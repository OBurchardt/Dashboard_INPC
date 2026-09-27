# Etapa 3.0: Pacote do assistente
# O chat da versão online não pode ler números de figura nem de texto arredondado, então junto aqui, num JSON só,
# os mesmos resultados que alimentam o dashboard: o catálogo das séries (componentes, genéricos e os itens que
# saíram da cesta 2018), os valores sem arredondar além das 6 casas de sempre, o que cada métrica é e como foi
# conferida, o release, as expectativas registradas, a estimativa do mês, o registro das visualizações que o chat
# pode abrir e os trechos da metodologia. Não faço conta nova: só seleciono e organizo o que as métricas já
# calcularam. O snapshot_id é o hash do conteúdo; o servidor recusa pergunta feita sobre outro snapshot.

import hashlib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p


# ==== 1. Leitura ====
def ler_parquet(nome):
    """Uma tabela de data/processed."""
    return pd.read_parquet(p.PASTA_PROCESSED / f"{nome}.parquet")


def ler_json(nome):
    """Um JSON de data/processed."""
    return json.loads((p.PASTA_PROCESSED / nome).read_text(encoding="utf-8"))


def limpo(valor):
    """Número com as 6 casas do resumo, ou None onde não há dado (nunca zero no lugar de ausente)."""
    return None if pd.isna(valor) else round(float(valor), 6)


def normalizado(texto):
    """Minúsculas, sem acento: a chave de comparação de nomes."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


# ==== 2. Métricas: o que cada uma é e como foi conferida ====
def situacao_da_validacao(validacao, release):
    """O status de cada tipo de conferência, a partir do validacao.json e do escopo da docs/auditoria.md."""
    checagens = validacao["checagens"]
    auditado = release == p.RELEASE_AUDITADO
    auditoria = {"status": "conferido_na_auditoria" if auditado else "metodo_conferido_na_auditoria",
                 "escopo": "auditoria de 27/09/2026 sobre o release da 1ª quinz. set/26 (docs/auditoria.md)"
                           + ("" if auditado else "; o release atual é posterior, então só o método foi conferido")}
    tabulado = checagens["ultimo release vs tabulado oficial"]
    aditividade = checagens["incidencias somam o INPC geral (24 meses)"]
    return {
        "tabulado": {"status": "validado_no_release" if tabulado["ok"] else "reprovado", "desvio_maximo_pp": tabulado["desvio_maximo_pp"],
                     "escopo": "variação, 12 meses e incidência dos 16 componentes no último período de cada frequência, contra os tabulados CA55 e CA56 do INEGI; "
                               "o histórico dos 7 componentes principais foi conferido na auditoria contra o BIE, e o dos 9 subíndices em 12 períodos"},
        "aditividade": {"status": "validado_no_release" if aditividade["ok"] else "reprovado", "desvio_maximo_pp": aditividade["desvio_maximo_pp"],
                        "escopo": "a incidência do núcleo mais a do não núcleo dá a variação do INPC nos últimos 24 meses"},
        "auditoria": auditoria,
        "externa": {"status": "fonte_externa_sem_conferencia", "escopo": "número digitado ou baixado de fora do INEGI; o pipeline só registra a fonte"},
    }


def catalogo_de_metricas(validacoes):
    """Nome, unidade, natureza (observado, derivado, estimado), fonte, validação e trecho da metodologia de cada métrica."""
    inegi, projeto = "INEGI (app Índices de Precios)", "cálculo do projeto sobre dados do INEGI"
    def metrica(nome, unidade, natureza, fonte, validacao, tema, **extra):
        return {"nome": nome, "unidade": unidade, "natureza": natureza, "fonte": fonte, "validacao": validacoes[validacao], "tema_metodologia": tema, **extra}
    # nos genéricos a validação do release não se aplica: o tabulado só tem os 16 componentes, e a incidência do
    # genérico é calculada pelo projeto com o peso efetivo (conferida na auditoria contra o quadro 2 dos boletins)
    genericos = {"natureza": "derivado", "fonte": projeto + " (peso efetivo da cesta 2024)", "validacao": validacoes["auditoria"]}
    observado_generico = {"natureza": "observado", "fonte": inegi, "validacao": validacoes["auditoria"]}
    return {
        "indice": metrica("índice (base 2ª quinz. jul/2018 = 100)", "índice", "observado", inegi, "tabulado", "fontes", para_genericos=observado_generico),
        "variacao_periodo": metrica("variação no período (mês ou quinzena contra o anterior)", "%", "observado", inegi, "tabulado", "mensal_e_quinzenal", para_genericos=observado_generico),
        "variacao_anual": metrica("variação em 12 meses (12 meses ou 24 quinzenas)", "%", "observado", inegi, "tabulado", "mensal_e_quinzenal", para_genericos=observado_generico),
        "incidencia_periodo": metrica("contribuição no período (incidência): pp da variação do INPC no período", "pp", "observado", "INEGI (incidência publicada)", "aditividade", "incidencia", para_genericos=genericos),
        "contribuicao_anual": metrica("contribuição para a variação em 12 meses do INPC", "pp", "derivado", projeto, "auditoria", "contribuicao_12_meses"),
        "contribuicao_no_pai": metrica("contribuição para a variação em 12 meses do pai", "pp", "derivado", projeto, "auditoria", "contribuicao_no_pai"),
        "contribuicao_no_grupo": metrica("contribuição para a variação em 12 meses do núcleo ou do não núcleo", "pp", "derivado", projeto, "auditoria", "contribuicao_no_pai"),
        "norma_mediana": metrica("padrão sazonal: mediana da variação no mesmo mês ou quinzena, 2010–2019", "%", "derivado", projeto, "auditoria", "padrao_sazonal"),
        "norma_p25": metrica("padrão sazonal: percentil 25, 2010–2019", "%", "derivado", projeto, "auditoria", "padrao_sazonal"),
        "norma_p75": metrica("padrão sazonal: percentil 75, 2010–2019", "%", "derivado", projeto, "auditoria", "padrao_sazonal"),
        "norma_n": metrica("anos de 2010–2019 com dado na posição do ano (amostra do padrão sazonal)", "anos", "derivado", projeto, "auditoria", "padrao_sazonal"),
        "desvio_norma": metrica("variação menos a mediana sazonal (não é surpresa contra expectativa)", "pp", "derivado", projeto, "auditoria", "padrao_sazonal"),
        "desvio_sazonal_ponderado": metrica("desvio sazonal vezes o peso efetivo: pp do INPC fora do padrão sazonal", "pp", "derivado", projeto, "auditoria", "desvio_sazonal_ponderado"),
        "variacao_sa_mensal": metrica("variação mensal dessazonalizada (STL do projeto, não é série oficial do INEGI)", "%", "derivado", projeto, "auditoria", "ajuste_sazonal",
                                      limitacao="a ponta muda quando entra um mês novo"),
        "saar_3m": metrica("variação dessazonalizada anualizada de 3 meses (SAAR, STL do projeto)", "%", "derivado", projeto, "auditoria", "saar",
                           limitacao="a ponta revisa em média 1,25 pp (núcleo) quando entra um mês novo"),
        "saar_6m": metrica("variação dessazonalizada anualizada de 6 meses (SAAR, STL do projeto)", "%", "derivado", projeto, "auditoria", "saar",
                           limitacao="a ponta revisa em média 1,00 pp (núcleo) quando entra um mês novo"),
        "pct_cesta_em_alta": metrica("parte do peso da cesta com alta no mês", "% do peso", "derivado", projeto, "auditoria", "difusao"),
        "pct_cesta_anual_acima_3": metrica("parte do peso da cesta com alta acima de 3% em 12 meses", "% do peso", "derivado", projeto, "auditoria", "difusao"),
        "cobertura_peso_mes": metrica("cobertura do peso da cesta na medida de alta no mês", "% do peso", "derivado", projeto, "auditoria", "difusao"),
        "cobertura_peso_anual": metrica("cobertura do peso da cesta na medida de 12 meses", "% do peso", "derivado", projeto, "auditoria", "difusao"),
    }


# ==== 3. Catálogo das séries ====
def aliases():
    """Os nomes em português que a busca aceita, por id de série."""
    tabela = pd.read_csv(p.ALIASES_SERIES, dtype=str, encoding="utf-8")
    return tabela.groupby("id_serie")["alias"].apply(list).to_dict()


def cobertura(tabela, chave, valor):
    """Primeiro e último período com dado, por frequência."""
    linhas = tabela[tabela[chave] == valor]
    return {frequencia: [grupo["periodo"].min(), grupo["periodo"].max()] for frequencia, grupo in linhas.groupby("frequencia")}


def series_componentes(componentes, nomes_extra):
    """Os 16 componentes do catálogo do INEGI, com hierarquia e filhos."""
    catalogo = pd.read_csv(p.CATALOGO, dtype=str, encoding="utf-8")
    catalogo = catalogo[(catalogo["tipo"] == "indice") & (catalogo["frequencia"] == "mensal")]
    filhos = catalogo.dropna(subset=["pai"]).groupby("pai")["componente"].apply(list).to_dict()
    return [{"id": linha.componente, "tipo": "componente", "nome_oficial": linha.nome, "nome_exibicao": p.NOMES_EXIBICAO[linha.componente],
             "aliases": nomes_extra.get(linha.componente, []), "nivel": int(linha.nivel), "pai": linha.pai if isinstance(linha.pai, str) else None,
             "filhos": filhos.get(linha.componente, []), "cobertura": cobertura(componentes, "componente", linha.componente),
             "cestas": ["2018", "2024"]} for linha in catalogo.itertuples()]


def series_genericos(genericos, ponderadores, nomes_extra):
    """Os 292 genéricos da cesta 2024 e os 28 da cesta 2018 que saíram, estes sem série."""
    cesta_2024 = ponderadores[ponderadores["cesta"] == "2024"]
    cesta_2018 = ponderadores[ponderadores["cesta"] == "2018"]
    codigos_2018 = set(cesta_2018["codigo_generico"].dropna())
    series = [{"id": f"g{linha.codigo_generico}", "tipo": "generico", "nome_oficial": linha.nome_generico, "nome_exibicao": linha.nome_generico,
               "aliases": nomes_extra.get(f"g{linha.codigo_generico}", []), "nivel": 4, "pai": linha.subindice, "filhos": [],
               "codigo_generico": linha.codigo_generico, "peso_cesta_2024": limpo(linha.ponderador),
               "cobertura": cobertura(genericos, "codigo_generico", linha.codigo_generico),
               "cestas": ["2018", "2024"] if linha.codigo_generico in codigos_2018 else ["2024"]}
              for linha in cesta_2024.itertuples()]
    # quem saiu da cesta 2018 existe na busca, para o assistente dizer que não há série em vez de trocar por outro item
    series += [{"id": "c2018_" + re.sub(r"[^a-z0-9]+", "_", normalizado(linha.nome_generico)).strip("_"), "tipo": "generico_saido", "nome_oficial": linha.nome_generico,
                "nome_exibicao": linha.nome_generico, "aliases": [], "nivel": 4, "pai": linha.subindice, "filhos": [], "peso_cesta_2018": limpo(linha.ponderador),
                "cobertura": {}, "cestas": ["2018"]} for linha in cesta_2018[cesta_2018["codigo_generico"].isna()].itertuples()]
    return series


def series_indicadores(difusao):
    """A difusão, que não é série do INEGI mas um indicador do projeto sobre os genéricos."""
    return [{"id": "difusao", "tipo": "indicador", "nome_oficial": "Difusão", "nome_exibicao": "Difusão", "aliases": ["difusão", "espalhamento"],
             "nivel": None, "pai": None, "filhos": [], "cobertura": {"mensal": [difusao["periodo"].min(), difusao["periodo"].max()]}, "cestas": ["2018", "2024"]}]


# ==== 4. Valores ====
COLUNAS_COMPONENTES = ["indice", "variacao_periodo", "variacao_anual", "incidencia_periodo", "contribuicao_anual", "contribuicao_no_pai",
                       "contribuicao_no_grupo", "norma_mediana", "norma_p25", "norma_p75", "norma_n", "desvio_norma",
                       "variacao_sa_mensal", "saar_3m", "saar_6m"]
COLUNAS_GENERICOS = ["indice", "variacao_periodo", "variacao_anual", "incidencia_periodo", "norma_mediana", "norma_p25", "norma_p75", "norma_n",
                     "desvio_norma", "desvio_sazonal_ponderado"]
COLUNAS_DIFUSAO = ["pct_cesta_em_alta", "pct_cesta_anual_acima_3", "cobertura_peso_mes", "cobertura_peso_anual"]


def colunas_da_serie(linhas, colunas):
    """Uma série em colunas: períodos, rótulos e uma lista por métrica, na ordem do tempo."""
    linhas = linhas.sort_values("periodo")
    valores = {"periodos": linhas["periodo"].tolist(), "rotulos": linhas["rotulo_periodo"].tolist()}
    valores.update({coluna: [limpo(v) for v in linhas[coluna]] for coluna in colunas if linhas[coluna].notna().any()})
    return valores


def valores(componentes, genericos, difusao):
    """Todos os valores, por id de série e frequência; componentes desde o início da dessazonalização, genéricos nos 24 meses do pipeline."""
    recentes = componentes[componentes["data"].dt.year >= p.ANO_INICIO_DESSAZONALIZACAO]
    resultado = {}
    for (componente, frequencia), linhas in recentes.groupby(["componente", "frequencia"]):
        resultado.setdefault(componente, {})[frequencia] = colunas_da_serie(linhas, COLUNAS_COMPONENTES)
    for (codigo, frequencia), linhas in genericos.groupby(["codigo_generico", "frequencia"]):
        resultado.setdefault(f"g{codigo}", {})[frequencia] = colunas_da_serie(linhas, COLUNAS_GENERICOS)
    resultado["difusao"] = {"mensal": colunas_da_serie(difusao, COLUNAS_DIFUSAO)}
    return resultado


# ==== 5. Release, expectativas e estimativa ====
def release(resumo):
    """Qual divulgação está no painel e o que ela traz."""
    frequencia = resumo["frequencia_do_release"]
    return {"tipo": resumo["tipo_ultimo_release"], "frequencia_do_release": frequencia, "periodo": resumo["ultimo_periodo"][frequencia],
            "rotulo": resumo["ultimo_rotulo"][frequencia], "ultimo_periodo": resumo["ultimo_periodo"], "ultimo_rotulo": resumo["ultimo_rotulo"],
            "descricao": "1ª quinzena: só a quinzena é nova; o mês ainda não fechou" if resumo["tipo_ultimo_release"] == "1a_quinzena"
                         else "mensal: o mês fechado e a 2ª quinzena saem juntos"}


def expectativas(resumo):
    """As expectativas de mercado registradas para o release e para o mês da estimativa, com fonte; nada além disso existe."""
    registradas = []
    def acrescentar(periodo, rotulo, indicadores, realizado):
        for indicador, item in indicadores.items():
            registradas.append({"periodo": periodo, "rotulo_periodo": rotulo, "indicador": indicador, "esperado": item["esperado"],
                                "realizado": item.get("realizado") if realizado else None, "fonte": item["fonte"], "unidade": "%"})
    esperada = resumo["expectativa"]
    acrescentar(esperada["periodo"], esperada["rotulo_periodo"], esperada["indicadores"], True)
    if resumo["mensal_implicito"]:
        implicito = resumo["mensal_implicito"]
        acrescentar(implicito["mes"], implicito["rotulo_mes"], implicito["expectativa"], False)
    return registradas


# ==== 6. Registro das visualizações ====
def cards_do_template():
    """Os cards do template.html: aba, espaço, título, subtítulo e se é tabela."""
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    cards = []
    for aba, corpo in re.findall(r'<section class="painel[^"]*" id="(\w+)">(.*?)</section>', template, re.S):
        padrao = r'<div class="card c\d+" data-card="(\w+)"( data-tipo="tabela")?>\s*<h3>(.*?)</h3><p class="sub">(.*?)</p>'
        cards += [{"aba": aba, "id": slot, "tipo": "tabela" if tabela else "grafico", "titulo": titulo, "subtitulo": sub}
                  for slot, tabela, titulo, sub in re.findall(padrao, corpo, re.S)]
    return cards


def cards_do_explorar(graficos):
    """Os cards da aba Explorar, que o template monta a partir dos gráficos: dois por categoria."""
    cards = []
    for slot in graficos:
        if slot.startswith("explorar_") and slot.endswith("_anual"):
            meta = graficos[slot]["layout"]["meta"]
            bloco = slot.removesuffix("_anual")
            cards.append({"aba": "explorar", "id": slot, "tipo": "grafico", "titulo": f"{meta['bloco']}: variação em 12 meses", "subtitulo": meta.get("subtitulo", "")})
            cards.append({"aba": "explorar", "id": f"{bloco}_contrib", "tipo": "grafico", "titulo": f"{meta['bloco']}: contribuições", "subtitulo": ""})
    return cards


def metricas_da_visualizacao(slot):
    """Que métricas cada visualização mostra; o mesmo nome das colunas do pacote."""
    if slot in ("main_inpc_meta", "main_core_meta") or slot.endswith("_anual"):
        return ["variacao_anual"]
    if slot == "grupos_nao_nucleo_desde_base":
        return ["contribuicao_no_grupo"]
    if slot.endswith("_contrib"):
        return ["contribuicao_no_pai", "variacao_anual"]
    return {"main_vs_norma": ["variacao_periodo", "norma_mediana", "norma_p25", "norma_p75"], "decomp_arvore": ["incidencia_periodo"],
            "tend_dessazonalizado": ["variacao_sa_mensal"], "tend_momentum": ["saar_6m", "saar_3m", "variacao_anual"],
            "tend_difusao": ["pct_cesta_em_alta", "pct_cesta_anual_acima_3"],
            "main_ultimos_periodos": ["variacao_periodo", "norma_mediana", "variacao_anual"],
            "main_top_incidencias": ["variacao_periodo", "incidencia_periodo"],
            "decomp_desvios": ["variacao_periodo", "norma_mediana", "desvio_sazonal_ponderado"]}.get(slot, ["variacao_periodo", "norma_mediana", "norma_p25", "norma_p75"])


def series_do_grafico(figura, codigo_por_nome):
    """Quem aparece num gráfico, pelo meta de cada traço; as aberturas viram o id do genérico pelo nome."""
    series = {}
    for traco in figura["data"]:
        meta = traco.get("meta") or {}
        componente = meta.get("componente")
        nome = str(traco.get("name", "")).split(" · ")[0]
        if componente in p.NOMES_EXIBICAO:
            series[componente] = p.NOMES_EXIBICAO[componente]
        elif componente and componente.startswith("abertura_") and normalizado(nome) in codigo_por_nome:
            series[f"g{codigo_por_nome[normalizado(nome)]}"] = nome
    return [{"serie_id": serie, "rotulo": rotulo} for serie, rotulo in series.items()]


def series_da_tabela(slot, resumo):
    """As linhas de cada tabela: os componentes da tabela do último release, ou os genéricos dos destaques."""
    destaques = resumo["destaques"]
    if slot == "main_ultimos_periodos":
        return [{"serie_id": c, "rotulo": p.NOMES_EXIBICAO[c]} for c in (*p.COMPONENTES_PRINCIPAIS, *p.COMPONENTES_NIVEL_2)]
    chaves = {"main_top_incidencias": ("maiores_incidencias", "menores_incidencias"), "decomp_desvios": ("acima_da_norma", "abaixo_da_norma")}[slot]
    return [{"serie_id": f"g{item['codigo_generico']}", "rotulo": item["nome_generico"]} for chave in chaves for item in destaques[chave]]


def series_sem_componente_no_traco(card, figura):
    """Os gráficos cujos traços não são componentes: o perfil sazonal (um traço por ano), a árvore e a difusão."""
    if card["id"] == "decomp_arvore":
        return [{"serie_id": c, "rotulo": p.NOMES_EXIBICAO[c]} for c in figura["data"][0]["ids"] if c in p.NOMES_EXIBICAO]
    if card["id"] == "tend_difusao":
        return [{"serie_id": "difusao", "rotulo": "Difusão"}]
    # o perfil é de um componente só, que está no título ("Perfil sazonal: Núcleo"; o do INPC diz "do INPC")
    nome = card["titulo"].split(": ")[-1]
    componente = "indice_general" if card["id"] == "tend_perfil_sazonal" else next(c for c, n in p.NOMES_EXIBICAO.items() if n == nome)
    return [{"serie_id": componente, "rotulo": p.NOMES_EXIBICAO[componente]}]


def janela_do_grafico(figura):
    """Primeira e última data do eixo x, quando o eixo é de datas."""
    datas = sorted(str(x)[:10] for traco in figura["data"] for x in (traco.get("x") or []) if re.match(r"\d{4}-\d{2}-\d{2}", str(x)))
    return [datas[0], datas[-1]] if datas else None


def frequencia_da_visualizacao(slot, figura, resumo):
    """Mensal, quinzenal ou mensal com o ponto da última quinzena, como o chip do card diz."""
    if slot in ("main_vs_norma", "decomp_arvore", "main_top_incidencias", "decomp_desvios", "main_ultimos_periodos"):
        return resumo["frequencia_do_release"]
    if figura and any((traco.get("meta") or {}).get("rotulo_quinzena") for traco in figura["data"]):
        return "mensal_com_ultima_quinzena"
    return "mensal"


def visualizacoes(graficos, resumo, ponderadores):
    """O registro declarativo do que o chat pode abrir: uma entrada por espaço, com as abas onde ele aparece."""
    cesta = ponderadores[ponderadores["cesta"] == "2024"]
    codigo_por_nome = dict(zip(cesta["nome_generico"].map(normalizado), cesta["codigo_generico"]))
    registro = {}
    for card in cards_do_template() + cards_do_explorar(graficos):
        if card["id"] in registro:  # o mesmo gráfico em duas abas (Resumo e Composição): a última é a de referência
            registro[card["id"]]["abas"].append(card["aba"])
            registro[card["id"]]["aba_principal"] = card["aba"]
            continue
        figura = graficos.get(card["id"])
        tabela = card["tipo"] == "tabela"
        series = series_da_tabela(card["id"], resumo) if tabela else series_do_grafico(figura, codigo_por_nome) or series_sem_componente_no_traco(card, figura)
        # destacar só faz sentido onde há mais de uma série para apagar em volta; a árvore e os perfis não têm isso
        destaques = ["linha"] if tabela else ["serie"] if len(series) > 1 and card["id"] != "decomp_arvore" else []
        registro[card["id"]] = {
            **card, "abas": [card["aba"]], "aba_principal": card["aba"], "series": series,
            "metricas": metricas_da_visualizacao(card["id"]), "frequencia": frequencia_da_visualizacao(card["id"], figura, resumo),
            "unidade": "pp" if card["id"] in ("decomp_arvore",) else "% e pp" if tabela else "%",
            "janela": None if tabela else janela_do_grafico(figura),
            "destaques_suportados": destaques,
            "filtros_suportados": [],  # as figuras não têm filtro nem janela ajustável; o chat não finge que têm
        }
        registro[card["id"]].pop("aba")
    return list(registro.values())


# ==== 7. Metodologia ====
DOCUMENTOS = ["metodologia.md", "guia_do_projeto.md", "auditoria.md"]
# cada tema aponta para trechos pelo começo do texto (ou pela seção inteira, com None); se um documento mudar e o
# trecho sumir, a etapa para, para o assistente nunca citar um trecho que não existe
TEMAS = {
    "fontes": [("metodologia.md", "Fonte dos dados", None)],
    "mensal_e_quinzenal": [("metodologia.md", None, "O índice mensal é a média das duas quinzenas"), ("guia_do_projeto.md", None, "Variações (`acrescentar_variacoes`)"),
                           ("metodologia.md", None, "O quinzenal não é dessazonalizado")],
    "incidencia": [("guia_do_projeto.md", None, "Incidência: a dos componentes"), ("guia_do_projeto.md", None, "Com o jitomate na 1ª quinzena de setembro")],
    "contribuicao_12_meses": [("guia_do_projeto.md", None, "Contribuição para a inflação em 12 meses"), ("metodologia.md", None, "Contribuição anual pela identidade exata")],
    "contribuicao_no_pai": [("guia_do_projeto.md", None, "Contribuição para o pai"), ("guia_do_projeto.md", None, "Na 1ª quinzena de agosto de 2026: serviços"),
                            ("guia_do_projeto.md", None, "Aberturas dos subíndices")],
    "padrao_sazonal": [("guia_do_projeto.md", None, "Norma sazonal (`acrescentar_norma`)"), ("metodologia.md", None, "Desvio sazonal, não surpresa")],
    "desvio_sazonal_ponderado": [("guia_do_projeto.md", None, "Desvio sazonal ponderado"), ("metodologia.md", None, "Desvio sazonal, não surpresa")],
    "ajuste_sazonal": [("guia_do_projeto.md", None, "`dessazonalizar` aplica o STL"), ("metodologia.md", None, "SAAR: os últimos pontos mudam"),
                       ("metodologia.md", None, "O quinzenal não é dessazonalizado")],
    "saar": [("guia_do_projeto.md", None, "Ritmo dessazonalizado"), ("metodologia.md", None, "SAAR: os últimos pontos mudam")],
    "difusao": [("guia_do_projeto.md", None, "Difusão (`serie_difusao`)"), ("metodologia.md", None, "Difusão com conjunto válido por medida")],
    "estimativa_do_mes": [("guia_do_projeto.md", None, "Estimativa do mês (`mensal_implicito`"), ("metodologia.md", None, "Estimativa do mês, com faixa pelos erros")],
    "expectativas": [("metodologia.md", None, "As expectativas do destaque"), ("guia_do_projeto.md", None, "Resumo (`numeros_principais`")],
    "cestas_e_genericos": [("metodologia.md", None, "Planilhas de ponderadores"), ("metodologia.md", None, "15 genéricos foram criados na cesta 2024"),
                           ("metodologia.md", None, "Na cesta 2018, 28 genéricos"), ("metodologia.md", None, "Os genéricos reproduzem o INPC")],
    "validacao": [("guia_do_projeto.md", "7. Validação", None), ("metodologia.md", None, "Validação sem nulo")],
    "auditoria": [("auditoria.md", "Resumo", None), ("auditoria.md", "Reauditoria", None)],
    "limitacoes": [("guia_do_projeto.md", "8. Limitações", None)],
    "vocabulario": [("guia_do_projeto.md", "Vocabulário", None)],
}


def trechos_do_documento(arquivo):
    """Um documento em trechos: cada item de lista e cada parágrafo (com o bloco de código ou a tabela que o segue) é um trecho."""
    trechos, secao, atual, em_codigo, depois_de_branco = [], "", [], False, False
    def fechar():
        if atual:
            trechos.append({"arquivo": arquivo, "secao": secao, "texto": "\n".join(atual).strip()})
            atual.clear()
    for linha in (p.RAIZ / "docs" / arquivo).read_text(encoding="utf-8").splitlines():
        if em_codigo or linha.startswith("```"):
            em_codigo = em_codigo != linha.startswith("```")  # o bloco de código fica com o parágrafo que o apresenta
            atual.append(linha)
        elif linha.startswith("#"):
            fechar()
            secao = linha.lstrip("#").strip()
        elif not linha.strip():
            depois_de_branco = True
            continue
        else:
            # item de lista, ou parágrafo novo depois de linha em branco, abre trecho; a tabela fica com o parágrafo de antes
            if re.match(r"(- |\d+\. )", linha) or (depois_de_branco and not linha.startswith("|")):
                fechar()
            atual.append(linha)
        depois_de_branco = False
    fechar()
    return trechos


def metodologia():
    """Os trechos dos três documentos, com id estável, e o índice de temas."""
    trechos = []
    for arquivo in DOCUMENTOS:
        for numero, trecho in enumerate(trechos_do_documento(arquivo), 1):
            trechos.append({"id": f"{arquivo.removesuffix('.md')}-{numero:03d}", **trecho})
    temas = {}
    for tema, alvos in TEMAS.items():
        ids = []
        for arquivo, secao, comeco in alvos:
            achados = [t["id"] for t in trechos if t["arquivo"] == arquivo and (secao is None or t["secao"].startswith(secao))
                       and (comeco is None or re.sub(r"^(- |\d+\. )", "", t["texto"]).startswith(comeco))]
            if not achados:
                raise SystemExit(f"Pacote do assistente: o tema {tema} aponta para um trecho que não existe mais em {arquivo} ({secao or comeco}).")
            ids += [i for i in achados if i not in ids]
        temas[tema] = ids
    versao = hashlib.sha256("".join((p.RAIZ / "docs" / a).read_text(encoding="utf-8") for a in DOCUMENTOS).encode()).hexdigest()[:12]
    return {"versao": versao, "temas": temas, "trechos": trechos}


# ==== 8. Snapshot e gravação ====
def snapshot_id(pacote):
    """Hash do conteúdo, sem a hora de geração nem a da validação: o mesmo dado dá sempre o mesmo id."""
    sem_horas = {**pacote, "gerado_em": None, "validacao": {**pacote["validacao"], "data": None}}
    conteudo = json.dumps(sem_horas, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    inicio = time.time()
    componentes, genericos = ler_parquet("metricas_componentes"), ler_parquet("metricas_genericos")
    difusao, ponderadores = ler_parquet("metricas_difusao"), ler_parquet("ponderadores")
    resumo, validacao, graficos = ler_json("metricas_resumo.json"), ler_json("validacao.json"), ler_json("graficos.json")
    nomes_extra = aliases()
    dados_do_release = release(resumo)
    pacote = {
        "versao_pacote": 1,
        "gerado_em": pd.Timestamp.now(tz=p.FUSO).isoformat(timespec="seconds"),
        "release": dados_do_release,
        "validacao": {"data": validacao["data"], "checagens": validacao["checagens"]},
        "metricas": catalogo_de_metricas(situacao_da_validacao(validacao, dados_do_release["periodo"])),
        "series": series_componentes(componentes, nomes_extra) + series_genericos(genericos, ponderadores, nomes_extra) + series_indicadores(difusao),
        "valores": valores(componentes, genericos, difusao),
        "expectativas": expectativas(resumo),
        "estimativa_do_mes": resumo["mensal_implicito"],
        "destaques": resumo["destaques"],
        "parametros": {"anos_padrao_sazonal": list(p.ANOS_NORMA_SAZONAL), "minimo_anos_padrao_sazonal": p.MINIMO_ANOS_PADRAO_SAZONAL,
                       "meta_banxico": 3, "inicio_cesta_2024": p.INICIO_CESTA_2024, "meses_de_genericos": p.MESES_METRICAS_GENERICOS},
        "visualizacoes": visualizacoes(graficos, resumo, ponderadores),
        "metodologia": metodologia(),
    }
    pacote["snapshot_id"] = snapshot_id(pacote)
    (p.PASTA_PROCESSED / "pacote_assistente.json").write_text(json.dumps(pacote, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Pacote do assistente: snapshot {pacote['snapshot_id']}, {len(pacote['series'])} séries, {len(pacote['visualizacoes'])} visualizações, "
          f"{len(pacote['metodologia']['trechos'])} trechos de metodologia; {time.time() - inicio:.1f} s")
