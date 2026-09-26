# Etapa 1.2 — Tratamento
# Transforma o bruto de data/raw em tabelas limpas em data/processed (parquet). Só organiza:
# não calcula variação nem nada analítico. É o único lugar que interpreta os formatos do INEGI
# ("N/E", árvore de genéricos, planilhas de ponderadores, tabulados).
# Saídas: séries do catálogo em formato longo, índices dos 292 genéricos com a classificação
# oficial por subíndice, ponderadores das cestas 2018 e 2024, a hierarquia completa (para o
# drill-down do dashboard) e o tabulado oficial do último release em forma de tabela.

import json
import re
import time
import unicodedata

import pandas as pd

from config import parametros as p

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
COLUNAS_ROTULO = ["rotulo_periodo", "rotulo_curto", "rotulo_mes"]

# Vigência de cada cesta: a de 2024 entrou na 2a quinzena de julho de 2024.
CESTAS = {"2018": ("ponderadores_2018.xlsx", "2018-07-Q2", "2024-07-Q1"),
          "2024": ("ponderadores_2024.xlsx", "2024-07-Q2", None)}


# ==== 1. Leitura das tabelas brutas ====
def normalizar(nome):
    """Tira acento, maiúscula e pontuação, para casar o mesmo nome escrito de jeitos diferentes pelo INEGI."""
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def rotulos_do_periodo(periodo):
    """Rótulos de tela de um período: completo ('1ª quinz. ago/26'), curto para cabeçalho ('1ª q. ago') e o mês ('ago/26')."""
    mes = f"{MESES[int(periodo[5:7]) - 1]}/{periodo[2:4]}"
    if "-Q" not in periodo:
        return mes, mes, mes
    return f"{periodo[-1]}ª quinz. {mes}", f"{periodo[-1]}ª q. {mes[:3]}", mes


def data_do_periodo(periodo):
    """Data de um período: dia 1 no mensal e na 1a quinzena, dia 16 na 2a quinzena."""
    return pd.Timestamp(periodo[:7] + ("-16" if periodo.endswith("Q2") else "-01"))


def ler_tabela_raw(nome):
    """Lê data/raw/<nome>.csv em formato longo (periodo, id_serie, valor); 'N/E' e 'NA' são dados que o INEGI não publica."""
    tabela = pd.read_csv(p.PASTA_RAW / f"{nome}.csv", dtype=str, keep_default_na=False)
    longa = tabela.melt(id_vars="periodo", var_name="id_serie", value_name="valor")
    longa["valor"] = pd.to_numeric(longa["valor"].replace({"N/E": None, "NA": None}))
    longa["data"] = longa["periodo"].map(data_do_periodo)
    rotulos = {periodo: rotulos_do_periodo(periodo) for periodo in longa["periodo"].unique()}
    for posicao, coluna in enumerate(COLUNAS_ROTULO):
        longa[coluna] = longa["periodo"].map(lambda periodo: rotulos[periodo][posicao])
    # antes do início de cada série o INEGI preenche com N/E: esses períodos saem; lacunas no meio ficam como nulo
    longa = longa.sort_values(["id_serie", "data"])
    return longa[longa["valor"].notna().groupby(longa["id_serie"]).cummax()]


def ler_arvore(frequencia):
    """Genéricos da árvore do app: id da série, código de 3 dígitos e nome."""
    nos = json.loads((p.PASTA_RAW / f"arvore_genericos_{frequencia}.json").read_text(encoding="utf-8"))
    genericos = pd.DataFrame([no for no in nos if no["generico"]])
    genericos["codigo_generico"] = genericos["nome"].str[:3]
    genericos["nome_generico"] = genericos["nome"].str[4:].str.strip()
    return genericos[["id_serie", "codigo_generico", "nome_generico"]]


# ==== 2. Séries do catálogo ====
def montar_series(catalogo):
    """Componentes e incidências nas duas frequências, com os metadados do catálogo."""
    tabelas = [ler_tabela_raw(f"{nome}_{frequencia}") for nome in ("componentes", "incidencias") for frequencia in ("mensal", "quinzenal")]
    series = pd.concat(tabelas).merge(catalogo[["id_serie", "tipo", "componente", "nivel", "pai", "frequencia"]], on="id_serie")
    return series[["id_serie", "tipo", "componente", "nivel", "pai", "frequencia", "periodo", *COLUNAS_ROTULO, "data", "valor"]]


# ==== 3. Ponderadores e classificação dos genéricos ====
def ler_planilha_ponderadores(arquivo, subindices_por_nome):
    """Genéricos de um xlsx oficial: cada um tem um X na coluna do seu subíndice; a coluna 1 é o ponderador."""
    planilha = pd.read_excel(p.PASTA_RAW / arquivo, sheet_name="CCIF", header=None)
    concepto = planilha.index[planilha[0] == "Concepto"][0]
    nomes_das_colunas = planilha.loc[concepto + 2]  # a terceira linha do cabeçalho traz os nomes dos subíndices
    colunas = {coluna: subindices_por_nome[normalizar(nome)] for coluna, nome in nomes_das_colunas.items()
               if normalizar(nome) in subindices_por_nome}
    # só a cesta 2024 tem a coluna 2 com o fator de encadeamento (índice de 2Q jul/2024 / 100)
    tem_fator = str(planilha.loc[concepto, 2]).startswith("Factor")
    genericos = []
    for _, linha in planilha.iterrows():
        subindice = [nome for coluna, nome in colunas.items() if str(linha[coluna]).strip() == "X"]
        if subindice:
            genericos.append({"nome_generico": str(linha[0]).strip(), "ponderador": float(linha[1]), "subindice": subindice[0],
                              "fator_encadeamento": float(linha[2]) if tem_fator else float("nan")})
    return pd.DataFrame(genericos)


def montar_ponderadores(catalogo, arvore):
    """As duas cestas numa tabela; o código vem da árvore, casando pelo nome (na cesta 2018, só os genéricos que continuaram)."""
    subindices = catalogo[catalogo["nivel"] == 3].drop_duplicates("componente")
    subindices_por_nome = dict(zip(subindices["nome"].map(normalizar), subindices["componente"]))
    codigo_por_nome = dict(zip(arvore["nome_generico"].map(normalizar), arvore["codigo_generico"]))
    pai = dict(zip(catalogo["componente"], catalogo["pai"]))
    cestas = []
    for cesta, (arquivo, inicio, fim) in CESTAS.items():
        tabela = ler_planilha_ponderadores(arquivo, subindices_por_nome)
        tabela["codigo_generico"] = tabela["nome_generico"].map(normalizar).map(codigo_por_nome)
        tabela["componente_nivel2"] = tabela["subindice"].map(pai)
        tabela["componente_nivel1"] = tabela["componente_nivel2"].map(pai)
        cestas.append(tabela.assign(cesta=cesta, vigencia_inicio=inicio, vigencia_fim=fim))
    return pd.concat(cestas)[["cesta", "codigo_generico", "nome_generico", "ponderador", "subindice", "componente_nivel2",
                              "componente_nivel1", "fator_encadeamento", "vigencia_inicio", "vigencia_fim"]]


# ==== 4. Genéricos ====
def montar_genericos(ponderadores):
    """Índice de cada genérico por período, com a classificação oficial da cesta 2024."""
    classificacao = ponderadores[ponderadores["cesta"] == "2024"][["codigo_generico", "subindice", "componente_nivel2", "componente_nivel1"]]
    tabelas = []
    for frequencia in ("mensal", "quinzenal"):
        tabela = ler_tabela_raw(f"genericos_{frequencia}").merge(ler_arvore(frequencia), on="id_serie")
        tabelas.append(tabela.assign(frequencia=frequencia))
    genericos = pd.concat(tabelas).merge(classificacao, on="codigo_generico").rename(columns={"valor": "indice"})
    return genericos[["codigo_generico", "nome_generico", "subindice", "componente_nivel2", "componente_nivel1",
                      "frequencia", "periodo", *COLUNAS_ROTULO, "data", "indice"]]


# ==== 5. Hierarquia e tabulado oficial ====
def montar_hierarquia(catalogo, ponderadores):
    """Todos os nós do drill-down: componentes (níveis 0 a 3) e, abaixo de cada subíndice, os seus genéricos (nível 4)."""
    indices = catalogo[catalogo["tipo"] == "indice"]
    ids = indices.pivot(index="componente", columns="frequencia", values="id_serie")
    componentes = indices.drop_duplicates("componente").rename(columns={"componente": "id_no"})[["id_no", "nome", "nivel", "pai"]]
    genericos = ponderadores[ponderadores["cesta"] == "2024"].rename(columns={"codigo_generico": "id_no", "nome_generico": "nome", "subindice": "pai"})
    hierarquia = pd.concat([componentes.assign(tipo_no="componente"), genericos[["id_no", "nome", "pai"]].assign(nivel=4, tipo_no="generico")])
    series_genericos = {frequencia: ler_arvore(frequencia).set_index("codigo_generico")["id_serie"] for frequencia in ("mensal", "quinzenal")}
    for frequencia in ("mensal", "quinzenal"):
        hierarquia[f"id_serie_{frequencia}"] = hierarquia["id_no"].map(ids[frequencia]).fillna(hierarquia["id_no"].map(series_genericos[frequencia]))
    return hierarquia[["id_no", "tipo_no", "nome", "nivel", "pai", "id_serie_mensal", "id_serie_quinzenal"]]


def montar_tabulado_oficial(catalogo):
    """Variação no período, variação anual e incidência publicadas pelo INEGI no último release, por componente."""
    componente_por_nome = dict(zip(catalogo["nome"].map(normalizar), catalogo["componente"]))
    linhas = []
    for frequencia in ("mensal", "quinzenal"):
        tabulado = json.loads((p.PASTA_RAW / f"tabulado_{frequencia}.json").read_text(encoding="utf-8"))
        for linha in tabulado["Datos"]:
            linhas.append({"frequencia": frequencia, "periodo": tabulado["periodo"], "componente": componente_por_nome[normalizar(linha["descripcion"])],
                           "variacao": float(linha["valor_mensual"]), "variacao_anual": float(linha["valor_anual"]),
                           "incidencia": float(linha["valor_incidencia"])})
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    inicio = time.time()
    catalogo = pd.read_csv(p.CATALOGO, dtype={"id_serie": str, "pai": str})
    ponderadores = montar_ponderadores(catalogo, ler_arvore("mensal"))
    saidas = {"series": montar_series(catalogo), "genericos": montar_genericos(ponderadores), "ponderadores": ponderadores,
              "hierarquia": montar_hierarquia(catalogo, ponderadores), "tabulado_oficial": montar_tabulado_oficial(catalogo)}
    for nome, tabela in saidas.items():
        tabela.to_parquet(p.PASTA_PROCESSED / f"{nome}.parquet", index=False)
    print(f"Tratamento: {', '.join(f'{nome} {len(tabela)}' for nome, tabela in saidas.items())} linhas; {time.time() - inicio:.1f} s")
