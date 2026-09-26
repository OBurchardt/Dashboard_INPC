# Etapa 1.2: Tratamento
# Aqui o bruto vira tabela que dá para usar: tudo em formato longo (uma linha por série e período),
# com a data certa de cada quinzena e os rótulos que vão aparecer na tela. É o único lugar que
# entende as manias do INEGI: o "N/E" antes do começo das séries, o código de 3 dígitos no nome
# do genérico, o X da planilha de ponderadores e o JSON do tabulado. Não calculo nada analítico
# aqui; se eu precisar de uma variação, ela é conta da etapa de métricas.

import json
import re
import time
import unicodedata

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
COLUNAS_ROTULO = ["rotulo_periodo", "rotulo_curto", "rotulo_mes"]

# vigência de cada cesta; a de 2024 entrou na 2a quinzena de julho de 2024
CESTAS = {"2018": ("ponderadores_2018.xlsx", "2018-07-Q2", "2024-07-Q1"),
          "2024": ("ponderadores_2024.xlsx", "2024-07-Q2", None)}


# ==== 1. Leitura das tabelas brutas ====
def normalizar(nome):
    """Tiro acento, maiúscula e pontuação, porque o INEGI escreve o mesmo nome de jeitos diferentes em cada arquivo."""
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def rotulos_do_periodo(periodo):
    """Os três jeitos de escrever um período na tela: '1ª quinz. ago/26', '1ª q. ago' para cabeçalho estreito, e só o mês."""
    mes = f"{MESES[int(periodo[5:7]) - 1]}/{periodo[2:4]}"
    if "-Q" not in periodo:
        return mes, mes, mes
    return f"{periodo[-1]}ª quinz. {mes}", f"{periodo[-1]}ª q. {mes[:3]}", mes


def data_do_periodo(periodo):
    """A 1a quinzena vai para o dia 1 e a 2a para o dia 16, para as duas caberem no mesmo eixo de datas do mensal."""
    return pd.Timestamp(periodo[:7] + ("-16" if periodo.endswith("Q2") else "-01"))


def posicao_do_periodo(periodo):
    """Um número que sobe de 1 em 1 de um período para o seguinte; com ele um lag é uma subtração e um buraco na série aparece."""
    mes = int(periodo[:4]) * 12 + int(periodo[5:7]) - 1
    return mes * 2 + int(periodo[-1]) - 1 if "-Q" in periodo else mes


def ler_tabela_raw(nome):
    """Abro um CSV de data/raw e passo para o formato longo; 'N/E' e 'NA' são dado que o INEGI não publica."""
    tabela = pd.read_csv(p.PASTA_RAW / f"{nome}.csv", dtype=str, keep_default_na=False, encoding="utf-8")
    longa = tabela.melt(id_vars="periodo", var_name="id_serie", value_name="valor")
    longa["valor"] = pd.to_numeric(longa["valor"].replace({"N/E": None, "NA": None}))
    longa["data"] = longa["periodo"].map(data_do_periodo)
    longa["posicao"] = longa["periodo"].map(posicao_do_periodo)
    rotulos = {periodo: rotulos_do_periodo(periodo) for periodo in longa["periodo"].unique()}
    for posicao, coluna in enumerate(COLUNAS_ROTULO):
        longa[coluna] = longa["periodo"].map(lambda periodo: rotulos[periodo][posicao])
    # antes de uma série começar o INEGI preenche com N/E, e esses períodos eu jogo fora;
    # um buraco no meio (como as incidências de ago/2018, que o INEGI não publicou) fica como nulo
    longa = longa.sort_values(["id_serie", "data"])
    return longa[longa["valor"].notna().groupby(longa["id_serie"]).cummax()]


def ler_arvore(frequencia):
    """Da árvore só me interessam os genéricos: o id da série, o código de 3 dígitos e o nome sem o código."""
    nos = json.loads((p.PASTA_RAW / f"arvore_genericos_{frequencia}.json").read_text(encoding="utf-8"))
    genericos = pd.DataFrame([no for no in nos if no["generico"]])
    genericos["codigo_generico"] = genericos["nome"].str[:3]
    genericos["nome_generico"] = genericos["nome"].str[4:].str.strip()
    return genericos[["id_serie", "codigo_generico", "nome_generico"]]


# ==== 2. Séries do catálogo ====
def montar_series(catalogo):
    """Componentes e incidências nas duas frequências, com o nível e o pai de cada um tirados do catálogo."""
    tabelas = [ler_tabela_raw(f"{nome}_{frequencia}") for nome in ("componentes", "incidencias") for frequencia in ("mensal", "quinzenal")]
    series = pd.concat(tabelas).merge(catalogo[["id_serie", "tipo", "componente", "nivel", "pai", "frequencia"]], on="id_serie")
    return series[["id_serie", "tipo", "componente", "nivel", "pai", "frequencia", "periodo", "posicao", *COLUNAS_ROTULO, "data", "valor"]]


# ==== 3. Ponderadores e classificação dos genéricos ====
def ler_planilha_ponderadores(arquivo, subindices_por_nome):
    """Na planilha do INEGI cada genérico tem um X na coluna do seu subíndice; a coluna 1 é o peso."""
    planilha = pd.read_excel(p.PASTA_RAW / arquivo, sheet_name="CCIF", header=None)
    concepto = planilha.index[planilha[0] == "Concepto"][0]
    nomes_das_colunas = planilha.loc[concepto + 2]  # o cabeçalho tem três linhas; os nomes dos subíndices estão na terceira
    colunas = {coluna: subindices_por_nome[normalizar(nome)] for coluna, nome in nomes_das_colunas.items()
               if normalizar(nome) in subindices_por_nome}
    # só a planilha de 2024 tem, na coluna 2, o fator de encadeamento (o índice da 2Q jul/2024 dividido por 100)
    tem_fator = str(planilha.loc[concepto, 2]).startswith("Factor")
    genericos = []
    for _, linha in planilha.iterrows():
        subindice = [nome for coluna, nome in colunas.items() if str(linha[coluna]).strip() == "X"]
        if subindice:
            genericos.append({"nome_generico": str(linha[0]).strip(), "ponderador": float(linha[1]), "subindice": subindice[0],
                              "fator_encadeamento": float(linha[2]) if tem_fator else float("nan")})
    return pd.DataFrame(genericos)


def montar_ponderadores(catalogo, arvore):
    """As duas cestas numa tabela só; a planilha não traz código, então caso cada nome com o da árvore."""
    # na cesta 2018, 28 genéricos não existem mais na cesta 2024 e ficam sem código; eles são identificados pelo nome
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
    """O índice de cada genérico em cada período, já com o subíndice oficial da cesta 2024."""
    classificacao = ponderadores[ponderadores["cesta"] == "2024"][["codigo_generico", "subindice", "componente_nivel2", "componente_nivel1"]]
    tabelas = []
    for frequencia in ("mensal", "quinzenal"):
        tabela = ler_tabela_raw(f"genericos_{frequencia}").merge(ler_arvore(frequencia), on="id_serie")
        tabelas.append(tabela.assign(frequencia=frequencia))
    genericos = pd.concat(tabelas).merge(classificacao, on="codigo_generico").rename(columns={"valor": "indice"})
    return genericos[["codigo_generico", "nome_generico", "subindice", "componente_nivel2", "componente_nivel1",
                      "frequencia", "periodo", "posicao", *COLUNAS_ROTULO, "data", "indice"]]


# ==== 5. Tabulado oficial ====
def montar_tabulado_oficial(catalogo):
    """Os números que o INEGI publicou no release (variação, anual e incidência), numa tabela que a validação só compara."""
    componente_por_nome = dict(zip(catalogo["nome"].map(normalizar), catalogo["componente"]))
    linhas = []
    for frequencia in ("mensal", "quinzenal"):
        tabulado = json.loads((p.PASTA_RAW / f"tabulado_{frequencia}.json").read_text(encoding="utf-8"))
        for linha in tabulado["Datos"]:
            # o campo se chama "valor_mensual" também no quinzenal; é a variação contra o período anterior
            linhas.append({"frequencia": frequencia, "periodo": tabulado["periodo"], "componente": componente_por_nome[normalizar(linha["descripcion"])],
                           "variacao": float(linha["valor_mensual"]), "variacao_anual": float(linha["valor_anual"]),
                           "incidencia": float(linha["valor_incidencia"])})
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    inicio = time.time()
    catalogo = pd.read_csv(p.CATALOGO, dtype={"id_serie": str, "pai": str}, encoding="utf-8")
    ponderadores = montar_ponderadores(catalogo, ler_arvore("mensal"))
    saidas = {"series": montar_series(catalogo), "genericos": montar_genericos(ponderadores), "ponderadores": ponderadores,
              "tabulado_oficial": montar_tabulado_oficial(catalogo)}
    for nome, tabela in saidas.items():
        tabela.to_parquet(p.PASTA_PROCESSED / f"{nome}.parquet", index=False)
    print(f"Tratamento: {', '.join(f'{nome} {len(tabela)}' for nome, tabela in saidas.items())} linhas; {time.time() - inicio:.1f} s")
