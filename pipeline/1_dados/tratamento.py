"""
Etapa: 1.2 Tratamento
Faz: converte o bruto em tabelas limpas: séries do catálogo em formato longo (chave id da série
+ período padronizado), índices dos 292 genéricos com a classificação oficial por subíndice,
ponderadores das cestas 2018 e 2024 e a hierarquia completa para o drill-down. Só limpa,
padroniza e junta; não calcula variação nem nada analítico.
Lê: data/raw/ (manifesto, bie/, indicesdeprecios/, arvores/, ponderadores/), config/catalogo_series.csv
Escreve: data/processed/series.parquet, genericos.parquet, ponderadores.parquet, hierarquia.parquet
"""

import csv
import hashlib
import io
import json
import logging
import re
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))
from config import parametros  # noqa: E402

registro = logging.getLogger("tratamento")

FONTE_BIE = "inegi_bie"
FONTE_INDICESDEPRECIOS = "inegi_indicesdeprecios"
MESES_ESPANHOL = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
                  "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}
PADRAO_ROTULO_EXPORTADOR = re.compile(r"^(?:([12])Q )?(" + "|".join(MESES_ESPANHOL) + r") (\d{4})$")
PADRAO_PERIODO_BIE = re.compile(r"^(\d{4})/(\d{2})(?:/0([12]))?$")
PADRAO_GENERICO = re.compile(r"^(\d{3}) (.+)$")
COLUNAS_PERIODO = ["periodo", "data", "ano", "mes", "quinzena"]
COLUNAS_SERIES = ["id_serie", "fonte", "tipo", "uso", "componente", "nivel", "pai", "frequencia", *COLUNAS_PERIODO, "valor"]
COLUNAS_GENERICOS = ["codigo_generico", "nome_generico", "subindice", "componente_nivel2", "componente_nivel1", "frequencia",
                     *COLUNAS_PERIODO, "indice"]


class ErroDeFormato(ValueError):
    """Formato inesperado num arquivo bruto; a mensagem diz o arquivo e a linha."""


def ler_manifesto():
    """Não recebe nada; devolve o manifesto de data/raw (escrito pela ingestão)."""
    caminho = parametros.PASTA_RAW / parametros.NOME_MANIFESTO
    if not caminho.exists():
        raise FileNotFoundError("data/raw/manifesto.json não existe; rode a ingestão antes.")
    return json.loads(caminho.read_text(encoding="utf-8"))


def conferir_integridade(manifesto):
    """Recebe o manifesto; confere o sha256 de cada arquivo de data/raw contra o registrado pela ingestão. Não devolve nada; erro se divergir."""
    for relativo, entrada in manifesto["arquivos"].items():
        caminho = parametros.PASTA_RAW / relativo
        if not caminho.exists():
            raise FileNotFoundError(f"Arquivo do manifesto ausente: data/raw/{relativo}")
        if hashlib.sha256(caminho.read_bytes()).hexdigest() != entrada["sha256"]:
            raise ValueError(f"sha256 diferente do manifesto em data/raw/{relativo}; rode a ingestão de novo.")


def ler_catalogo():
    """Não recebe nada; devolve config/catalogo_series.csv como DataFrame (ids como texto)."""
    return pd.read_csv(parametros.ARQUIVO_CATALOGO, dtype=str, keep_default_na=False)


def normalizar_nome(texto):
    """Recebe um nome; devolve-o sem acento, minúsculo e só com letras e dígitos, para casar nomes entre fontes do INEGI."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def colunas_de_periodo(ano, mes, quinzena):
    """Recebe ano, mês e quinzena (ou None no mensal); devolve período ('AAAA-MM' ou 'AAAA-MM-Q1/Q2'), data e partes."""
    if quinzena is None:
        return f"{ano}-{mes:02d}", pd.Timestamp(ano, mes, 1), ano, mes, None
    return f"{ano}-{mes:02d}-Q{quinzena}", pd.Timestamp(ano, mes, parametros.DIA_INICIO_QUINZENA[quinzena]), ano, mes, quinzena


def interpretar_rotulo_exportador(rotulo, frequencia, arquivo, linha):
    """Recebe o rótulo de período do exportador ('Ago 2026', '1Q Sep 2026'), a frequência esperada e a posição; devolve (ano, mês, quinzena)."""
    encontrado = PADRAO_ROTULO_EXPORTADOR.match(rotulo.strip())
    if not encontrado:
        raise ErroDeFormato(f"{arquivo}, linha {linha}: rótulo de período inesperado {rotulo!r}")
    quinzena, mes, ano = encontrado.groups()
    if (quinzena is None) != (frequencia == "mensal"):
        raise ErroDeFormato(f"{arquivo}, linha {linha}: rótulo {rotulo!r} incompatível com a frequência {frequencia}")
    return int(ano), MESES_ESPANHOL[mes], (int(quinzena) if quinzena else None)


def interpretar_valor_exportador(texto, arquivo, linha):
    """Recebe o texto de uma célula do exportador e a posição; devolve float, ou None para os marcadores de ausência (N/E, NA)."""
    texto = texto.strip()
    if texto in parametros.MARCADORES_AUSENTES_EXPORTADOR:
        return None
    try:
        return float(texto)
    except ValueError:
        raise ErroDeFormato(f"{arquivo}, linha {linha}: valor inesperado {texto!r}") from None


def ler_csv_exportador(caminho, frequencia):
    """Recebe um CSV do exportador do app indicesdeprecios e sua frequência; devolve DataFrame longo (id_serie, ano, mes, quinzena, valor)."""
    arquivo = caminho.relative_to(RAIZ_PROJETO).as_posix()
    leitor = csv.reader(io.StringIO(caminho.read_bytes().decode(parametros.CODIFICACAO_EXPORTADOR)))
    ids, registros, estado = None, [], "prefacio"
    for linha in leitor:
        numero = leitor.line_num
        primeira = linha[0].strip() if linha else ""
        if estado == "prefacio":
            if primeira == "Título":
                estado = "cabecalho"
            continue
        if estado == "cabecalho":
            if primeira == "Cifra":
                continue
            if primeira != "Fecha":
                raise ErroDeFormato(f"{arquivo}, linha {numero}: esperava a linha 'Fecha' com os ids, veio {primeira!r}")
            ids = [valor.strip() for valor in linha[1:]]
            while ids and not ids[-1]:
                ids.pop()
            if not ids or not all(valor.isdigit() for valor in ids):
                raise ErroDeFormato(f"{arquivo}, linha {numero}: linha 'Fecha' sem ids numéricos")
            estado = "dados"
            continue
        if not linha or not any(valor.strip() for valor in linha):
            continue
        ano, mes, quinzena = interpretar_rotulo_exportador(primeira, frequencia, arquivo, numero)
        valores = linha[1:]
        while len(valores) > len(ids) and not valores[-1].strip():
            valores.pop()
        if len(valores) != len(ids):
            raise ErroDeFormato(f"{arquivo}, linha {numero}: {len(valores)} valores para {len(ids)} séries")
        for identificador, texto in zip(ids, valores):
            registros.append((identificador, ano, mes, quinzena, interpretar_valor_exportador(texto, arquivo, numero)))
    if ids is None:
        raise ErroDeFormato(f"{arquivo}: não encontrei as linhas 'Título' e 'Fecha'")
    return pd.DataFrame(registros, columns=["id_serie", "ano", "mes", "quinzena", "valor"])


def ler_json_bie(caminho, frequencia):
    """Recebe um JSON da API BIE (data/raw/bie/<id>.json) e a frequência; devolve DataFrame longo (id_serie, ano, mes, quinzena, valor texto)."""
    arquivo = caminho.relative_to(RAIZ_PROJETO).as_posix()
    serie = json.loads(caminho.read_text(encoding="utf-8"))["Series"][0]
    registros = []
    for posicao, observacao in enumerate(serie["OBSERVATIONS"]):
        encontrado = PADRAO_PERIODO_BIE.match(str(observacao["TIME_PERIOD"]).strip())
        if not encontrado:
            raise ErroDeFormato(f"{arquivo}, observação {posicao}: período inesperado {observacao['TIME_PERIOD']!r}")
        ano, mes, quinzena = int(encontrado.group(1)), int(encontrado.group(2)), encontrado.group(3)
        if (quinzena is None) != (frequencia == "mensal"):
            raise ErroDeFormato(f"{arquivo}, observação {posicao}: período {observacao['TIME_PERIOD']!r} incompatível com {frequencia}")
        valor = observacao["OBS_VALUE"]
        try:
            valor = None if valor in (None, "") else float(valor)
        except ValueError:
            raise ErroDeFormato(f"{arquivo}, observação {posicao}: valor inesperado {valor!r}") from None
        registros.append((serie["INDICADOR"], ano, mes, int(quinzena) if quinzena else None, valor))
    return pd.DataFrame(registros, columns=["id_serie", "ano", "mes", "quinzena", "valor"])


def acrescentar_periodo(tabela):
    """Recebe DataFrame com ano, mes e quinzena; devolve-o com periodo e data padronizados e quinzena como inteiro anulável."""
    partes = [colunas_de_periodo(int(ano), int(mes), None if pd.isna(quinzena) else int(quinzena))
              for ano, mes, quinzena in zip(tabela["ano"], tabela["mes"], tabela["quinzena"])]
    tabela = tabela.copy()
    tabela["periodo"] = [parte[0] for parte in partes]
    tabela["data"] = pd.to_datetime([parte[1] for parte in partes])
    tabela["quinzena"] = pd.array([parte[4] for parte in partes], dtype="Int64")
    tabela["ano"] = tabela["ano"].astype("int64")
    tabela["mes"] = tabela["mes"].astype("int64")
    return tabela


def remover_inicio_ausente(tabela, chaves, coluna_valor, descricao):
    """Recebe tabela longa, chaves da série e coluna de valor; devolve a tabela ordenada sem os ausentes do início de cada série e reporta os ausentes do meio."""
    tabela = tabela.sort_values([*chaves, "data"]).reset_index(drop=True)
    ja_comecou = tabela[coluna_valor].notna().groupby([tabela[chave] for chave in chaves]).cummax()
    tabela = tabela[ja_comecou].reset_index(drop=True)
    meio = tabela[tabela[coluna_valor].isna()]
    if len(meio):
        exemplos = meio.groupby(chaves).size().sort_values(ascending=False).head(5).to_dict()
        registro.info("  %s: %d valor(es) ausente(s) no meio de %d série(s), mantidos como nulo (ex.: %s)",
                      descricao, len(meio), meio.groupby(chaves).ngroups, exemplos)
    return tabela


def entradas_do_manifesto(manifesto, fonte, tipo_arquivo):
    """Recebe o manifesto, a fonte e o tipo de arquivo; devolve a lista de (caminho, entrada) correspondentes."""
    return [(parametros.PASTA_RAW / relativo, entrada) for relativo, entrada in manifesto["arquivos"].items()
            if entrada["fonte"] == fonte and entrada.get("tipo_arquivo") == tipo_arquivo]


def montar_series(manifesto, catalogo):
    """Recebe manifesto e catálogo; devolve series.parquet em formato longo (app e BIE), com metadados do catálogo e valores do BIE arredondados."""
    partes = []
    estruturas_catalogo = set(parametros.ESTRUTURAS_CATALOGO.values())
    for caminho, entrada in entradas_do_manifesto(manifesto, FONTE_INDICESDEPRECIOS, "series"):
        if entrada["estrutura"] in estruturas_catalogo:
            partes.append(ler_csv_exportador(caminho, entrada["frequencia"]).assign(fonte=FONTE_INDICESDEPRECIOS))
    for caminho, entrada in entradas_do_manifesto(manifesto, FONTE_BIE, "series"):
        partes.append(ler_json_bie(caminho, entrada["frequencia"]).assign(fonte=FONTE_BIE))
    longo = pd.concat(partes, ignore_index=True)
    metadados = catalogo[["id_serie", "fonte", "tipo", "uso", "componente", "nivel", "pai", "frequencia"]]
    series = longo.merge(metadados, on=["id_serie", "fonte"], how="inner", validate="many_to_one")
    faltando = set(zip(metadados["id_serie"], metadados["fonte"])) - set(zip(series["id_serie"], series["fonte"]))
    if faltando:
        raise ValueError(f"Séries do catálogo sem dados em data/raw: {sorted(faltando)}")
    for tipo, casas in parametros.CASAS_DECIMAIS_BIE.items():
        filtro = (series["fonte"] == FONTE_BIE) & (series["tipo"] == tipo)
        series.loc[filtro, "valor"] = series.loc[filtro, "valor"].round(casas)
    series["nivel"] = series["nivel"].astype("int64")
    series["pai"] = series["pai"].replace("", None)
    series = acrescentar_periodo(series)
    series = remover_inicio_ausente(series, ["fonte", "id_serie"], "valor", "series")
    return series[COLUNAS_SERIES]


def ler_arvores(manifesto):
    """Recebe o manifesto; devolve {frequencia: DataFrame dos genéricos da árvore (id_serie, codigo_generico, nome_generico)}."""
    genericos = {}
    for caminho, entrada in entradas_do_manifesto(manifesto, FONTE_INDICESDEPRECIOS, "arvore"):
        nos = json.loads(caminho.read_text(encoding="utf-8"))["nos"]
        linhas = []
        for no in nos:
            encontrado = PADRAO_GENERICO.match(no["nome"])
            if no["id_serie"] and encontrado:
                linhas.append((no["id_serie"], encontrado.group(1), encontrado.group(2).strip()))
        tabela = pd.DataFrame(linhas, columns=["id_serie", "codigo_generico", "nome_generico"])
        if tabela["codigo_generico"].duplicated().any() or len(tabela) != parametros.NUMERO_GENERICOS_ESPERADO:
            raise ValueError(f"{caminho.name}: {len(tabela)} genéricos (esperado {parametros.NUMERO_GENERICOS_ESPERADO}) ou códigos repetidos")
        genericos[entrada["frequencia"]] = tabela
    return genericos


def mapear_colunas_ponderadores(planilha, arquivo, componentes_por_nome):
    """Recebe a aba de ponderadores do INEGI (sem cabeçalho), o nome do arquivo e {nome normalizado: componente}; devolve (linha do cabeçalho, {coluna: papel})."""
    linhas_concepto = [indice for indice, valor in planilha[0].items() if str(valor).strip() == "Concepto"]
    if not linhas_concepto:
        raise ErroDeFormato(f"{arquivo}: não encontrei a linha de cabeçalho 'Concepto'")
    inicio = linhas_concepto[0]
    cabecalho = planilha.iloc[inicio:inicio + 3]
    papeis = {}
    for coluna in planilha.columns[1:]:
        rotulos = [str(valor).strip() for valor in cabecalho[coluna] if pd.notna(valor) and str(valor).strip()]
        escolhido = next((limpo for limpo in (re.sub(r"(?i)^total\s*", "", rotulo).strip() for rotulo in reversed(rotulos)) if limpo), None)
        if escolhido is None:
            continue
        normalizado = normalizar_nome(escolhido)
        if normalizado == normalizar_nome("Ponderador INPC"):
            papeis[coluna] = "ponderador"
        elif normalizado.startswith(normalizar_nome("Factor de encadenamiento")):
            papeis[coluna] = "fator_encadeamento"
        elif normalizado.startswith(normalizar_nome("Subíndice especial")):
            continue
        elif normalizado in componentes_por_nome:
            papeis[coluna] = componentes_por_nome[normalizado]
        else:
            raise ErroDeFormato(f"{arquivo}, linha {inicio + 1}, coluna {coluna}: cabeçalho não reconhecido {escolhido!r}")
    return inicio, papeis


def ler_planilha_ponderadores(cesta, catalogo):
    """Recebe a cesta ('2018' ou '2024') e o catálogo; devolve (genéricos com ponderador, subíndice e fator, fatores dos componentes) do xlsx oficial do INEGI."""
    arquivo = parametros.CESTAS[cesta]["arquivo"]
    caminho = parametros.PASTA_RAW / "ponderadores" / arquivo
    planilha = pd.read_excel(caminho, sheet_name=parametros.ABA_PONDERADORES, header=None, dtype=object)
    componentes = catalogo[(catalogo["fonte"] == FONTE_INDICESDEPRECIOS) & (catalogo["tipo"] == "indice") & (catalogo["frequencia"] == "mensal")]
    componentes_por_nome = {normalizar_nome(nome): componente for nome, componente in zip(componentes["nome"], componentes["componente"])}
    nivel_por_componente = dict(zip(componentes["componente"], componentes["nivel"].astype(int)))
    inicio, papeis = mapear_colunas_ponderadores(planilha, arquivo, componentes_por_nome)
    colunas_subindice = [coluna for coluna, papel in papeis.items() if nivel_por_componente.get(papel) == 3]
    coluna_ponderador = next(coluna for coluna, papel in papeis.items() if papel == "ponderador")
    coluna_fator = next((coluna for coluna, papel in papeis.items() if papel == "fator_encadeamento"), None)
    fatores_componentes, genericos = {}, []
    for indice in range(inicio + 3, len(planilha)):
        linha = planilha.iloc[indice]
        conceito = str(linha[0]).strip() if pd.notna(linha[0]) else ""
        if normalizar_nome(conceito) == normalizar_nome("Factor de encadenamiento"):
            fatores_componentes = {papel: float(linha[coluna]) for coluna, papel in papeis.items()
                                   if papel in nivel_por_componente and pd.notna(linha[coluna])}
            if coluna_fator is not None and pd.notna(linha[coluna_fator]):
                fatores_componentes["indice_general"] = float(linha[coluna_fator])
            continue
        marcados = [papeis[coluna] for coluna in colunas_subindice if str(linha[coluna]).strip().upper() == "X"]
        if not marcados:
            continue
        try:
            ponderador = float(linha[coluna_ponderador])
            fator = float(linha[coluna_fator]) if coluna_fator is not None else None
        except (TypeError, ValueError):
            raise ErroDeFormato(f"{arquivo}, linha {indice + 1}: ponderador ou fator não numérico para {conceito!r}") from None
        genericos.append({"nome_generico": conceito, "ponderador": ponderador, "fator_encadeamento": fator,
                          "subindice": "|".join(marcados)})
    tabela = pd.DataFrame(genericos)
    tabela["fator_encadeamento"] = tabela["fator_encadeamento"].astype("float64")
    repetidos = tabela["nome_generico"].map(normalizar_nome).duplicated()
    if repetidos.any():
        raise ErroDeFormato(f"{arquivo}: nomes de genérico repetidos após normalização: {list(tabela.loc[repetidos, 'nome_generico'])}")
    return tabela, fatores_componentes


def montar_ponderadores(catalogo, genericos_arvore):
    """Recebe o catálogo e os genéricos da árvore; devolve ponderadores.parquet (cestas 2018 e 2024), com código casado pelo nome da árvore e vigência."""
    codigo_por_nome = {normalizar_nome(nome): codigo for codigo, nome in
                       zip(genericos_arvore["codigo_generico"], genericos_arvore["nome_generico"])}
    if len(codigo_por_nome) != len(genericos_arvore):
        raise ValueError("Nomes de genéricos da árvore repetidos após normalização")
    pai = dict(zip(catalogo["componente"], catalogo["pai"]))
    partes, fatores = [], {}
    for cesta, configuracao in parametros.CESTAS.items():
        tabela, fatores[cesta] = ler_planilha_ponderadores(cesta, catalogo)
        tabela["codigo_generico"] = tabela["nome_generico"].map(lambda nome: codigo_por_nome.get(normalizar_nome(nome)))
        if cesta == parametros.CESTA_VIGENTE and tabela["codigo_generico"].isna().any():
            raise ValueError(f"Genéricos da cesta {cesta} sem par na árvore: {list(tabela.loc[tabela['codigo_generico'].isna(), 'nome_generico'])}")
        sem_codigo = int(tabela["codigo_generico"].isna().sum())
        if sem_codigo:
            registro.info("  cesta %s: %d genérico(s) sem equivalente na cesta vigente (código nulo, chave pelo nome)", cesta, sem_codigo)
        tabela["cesta"] = cesta
        tabela["componente_nivel2"] = tabela["subindice"].map(pai)
        tabela["componente_nivel1"] = tabela["componente_nivel2"].map(pai)
        tabela["vigencia_inicio"] = configuracao["vigencia_inicio"]
        tabela["vigencia_fim"] = configuracao["vigencia_fim"]
        partes.append(tabela)
    ponderadores = pd.concat(partes, ignore_index=True)[
        ["cesta", "codigo_generico", "nome_generico", "ponderador", "subindice", "componente_nivel2", "componente_nivel1",
         "fator_encadeamento", "vigencia_inicio", "vigencia_fim"]]
    return ponderadores.sort_values(["cesta", "codigo_generico", "nome_generico"]).reset_index(drop=True), fatores


def montar_genericos(manifesto, genericos_arvores, ponderadores):
    """Recebe manifesto, genéricos das árvores e ponderadores; devolve genericos.parquet (índice de cada genérico por período, com classificação oficial 2024)."""
    classificacao = ponderadores[ponderadores["cesta"] == parametros.CESTA_VIGENTE][
        ["codigo_generico", "subindice", "componente_nivel2", "componente_nivel1"]]
    estruturas_arvore = {configuracao["estrutura"]: frequencia for frequencia, configuracao in parametros.ARVORES_GENERICOS.items()}
    partes = []
    for caminho, entrada in entradas_do_manifesto(manifesto, FONTE_INDICESDEPRECIOS, "series"):
        frequencia = estruturas_arvore.get(entrada["estrutura"])
        if frequencia is None:
            continue
        longo = ler_csv_exportador(caminho, frequencia)
        longo = longo.merge(genericos_arvores[frequencia], on="id_serie", how="inner")
        faltando = set(genericos_arvores[frequencia]["id_serie"]) - set(longo["id_serie"])
        if faltando:
            raise ValueError(f"{caminho.name}: genéricos da árvore sem coluna no CSV: {sorted(faltando)[:10]}")
        partes.append(longo.assign(frequencia=frequencia))
    genericos = pd.concat(partes, ignore_index=True).rename(columns={"valor": "indice"})
    genericos = genericos.merge(classificacao, on="codigo_generico", how="left", validate="many_to_one")
    if genericos["subindice"].isna().any():
        raise ValueError(f"Genéricos sem classificação: {sorted(genericos.loc[genericos['subindice'].isna(), 'codigo_generico'].unique())}")
    genericos = acrescentar_periodo(genericos)
    genericos = remover_inicio_ausente(genericos, ["codigo_generico", "frequencia"], "indice", "genericos")
    return genericos[COLUNAS_GENERICOS]


def montar_hierarquia(catalogo, genericos_arvores, ponderadores, fatores):
    """Recebe catálogo, genéricos das árvores, ponderadores e fatores oficiais; devolve hierarquia.parquet com componentes (níveis 0 a 3) e genéricos (nível 4)."""
    principais = catalogo[(catalogo["fonte"] == FONTE_INDICESDEPRECIOS) & (catalogo["tipo"] == "indice")]
    componentes = principais[principais["frequencia"] == "mensal"][["componente", "nome", "nivel", "pai"]].copy()
    ids = principais.pivot(index="componente", columns="frequencia", values="id_serie")
    componentes["id_serie_mensal"] = componentes["componente"].map(ids["mensal"])
    componentes["id_serie_quinzenal"] = componentes["componente"].map(ids["quinzenal"])
    componentes["fator_encadeamento_2024"] = componentes["componente"].map(fatores[parametros.CESTA_VIGENTE])
    componentes = componentes.rename(columns={"componente": "id_no"}).assign(tipo_no="componente")
    vigentes = ponderadores[ponderadores["cesta"] == parametros.CESTA_VIGENTE].set_index("codigo_generico")
    genericos = genericos_arvores["mensal"][["codigo_generico", "nome_generico", "id_serie"]].rename(columns={"id_serie": "id_serie_mensal"})
    genericos = genericos.merge(genericos_arvores["quinzenal"][["codigo_generico", "id_serie"]].rename(columns={"id_serie": "id_serie_quinzenal"}),
                                on="codigo_generico", how="outer", validate="one_to_one")
    genericos = pd.DataFrame({"id_no": genericos["codigo_generico"], "nome": genericos["nome_generico"],
                              "nivel": parametros.NIVEL_GENERICO, "pai": genericos["codigo_generico"].map(vigentes["subindice"]),
                              "id_serie_mensal": genericos["id_serie_mensal"], "id_serie_quinzenal": genericos["id_serie_quinzenal"],
                              "fator_encadeamento_2024": genericos["codigo_generico"].map(vigentes["fator_encadeamento"]),
                              "tipo_no": "generico"})
    hierarquia = pd.concat([componentes, genericos], ignore_index=True)
    hierarquia["nivel"] = hierarquia["nivel"].astype("int64")
    hierarquia["pai"] = hierarquia["pai"].replace("", None)
    return hierarquia[["id_no", "tipo_no", "nome", "nivel", "pai", "id_serie_mensal", "id_serie_quinzenal", "fator_encadeamento_2024"]]


def salvar(tabela, caminho):
    """Recebe um DataFrame e o caminho; grava em parquet e registra no log o número de linhas. Não devolve nada."""
    tabela.to_parquet(caminho, index=False)
    registro.info("  %s: %d linhas", caminho.name, len(tabela))


def executar():
    """Não recebe nada; lê data/raw, monta as quatro tabelas e grava em data/processed. Devolve {nome do arquivo: número de linhas}."""
    inicio = time.time()
    parametros.criar_pastas()
    manifesto = ler_manifesto()
    conferir_integridade(manifesto)
    catalogo = ler_catalogo()

    series = montar_series(manifesto, catalogo)
    genericos_arvores = ler_arvores(manifesto)
    if set(genericos_arvores) != set(parametros.ARVORES_GENERICOS):
        raise ValueError(f"Árvores de genéricos ausentes no manifesto: {set(parametros.ARVORES_GENERICOS) - set(genericos_arvores)}")
    diferentes = set(zip(*genericos_arvores["mensal"][["codigo_generico", "nome_generico"]].values.T)) ^ \
        set(zip(*genericos_arvores["quinzenal"][["codigo_generico", "nome_generico"]].values.T))
    if diferentes:
        raise ValueError(f"Genéricos diferentes entre as árvores mensal e quinzenal: {sorted(diferentes)[:10]}")
    ponderadores, fatores = montar_ponderadores(catalogo, genericos_arvores["mensal"])
    genericos = montar_genericos(manifesto, genericos_arvores, ponderadores)
    hierarquia = montar_hierarquia(catalogo, genericos_arvores, ponderadores, fatores)

    saidas = {parametros.ARQUIVO_SERIES: series, parametros.ARQUIVO_GENERICOS: genericos,
              parametros.ARQUIVO_PONDERADORES: ponderadores, parametros.ARQUIVO_HIERARQUIA: hierarquia}
    for caminho, tabela in saidas.items():
        salvar(tabela, caminho)
    registro.info("Tratamento concluído em %.1f s", time.time() - inicio)
    return {caminho.name: len(tabela) for caminho, tabela in saidas.items()}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    resultado_tratamento = executar()
