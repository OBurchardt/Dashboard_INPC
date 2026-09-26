# Etapa 2.1 — Métricas
# Calcula os números que o economista lê no dia do release, a partir da base validada:
# variações, incidências e contribuições dos 16 componentes; comparação de cada período com a
# norma sazonal de 2010-2019; ritmo dessazonalizado anualizado (SAAR); as mesmas leituras para os
# 292 genéricos nos últimos 24 meses; e um resumo para o cabeçalho do dashboard (INPC, núcleo,
# mensal implícito no dia da 1a quinzena, difusão e destaques).
# Lê: data/processed (series, series_dessazonalizadas, genericos, ponderadores).
# Escreve: metricas_componentes.parquet, metricas_genericos.parquet, metricas_difusao.parquet e metricas_resumo.json.

import json
import time

import pandas as pd

from config import parametros as p

PERIODOS_POR_ANO = {"mensal": 12, "quinzenal": 24}
PRINCIPAIS = ("indice_general", "subyacente", "no_subyacente")


# ==== 1. Variações, norma sazonal e contribuições ====
def ler(nome):
    """Tabela de data/processed."""
    return pd.read_parquet(p.PASTA_PROCESSED / f"{nome}.parquet")


def acrescentar_variacoes(tabela, chave, periodos_no_ano):
    """Variação no período e em 12 meses (%), série a série, numa tabela em ordem cronológica."""
    anterior = tabela.groupby(chave)["indice"]
    tabela["variacao_periodo"] = (tabela["indice"] / anterior.shift(1) - 1) * 100
    tabela["variacao_anual"] = (tabela["indice"] / anterior.shift(periodos_no_ano) - 1) * 100
    return tabela


def acrescentar_norma(tabela, chave):
    """Mediana e quartis da variação do mesmo mês (ou quinzena) do ano em 2010-2019, e o desvio do dado atual."""
    # a norma diz quanto aquele período costuma subir; mediana e não média porque a janela tem
    # choques atípicos (ex.: jan/2017, liberalização da gasolina) que puxariam a média
    tabela["posicao_no_ano"] = tabela["periodo"].str[5:]  # "08" no mensal, "08-Q1" no quinzenal
    inicio, fim = p.ANOS_NORMA_SAZONAL
    janela = tabela[tabela["data"].dt.year.between(inicio, fim)]
    norma = janela.groupby([chave, "posicao_no_ano"])["variacao_periodo"].quantile([0.25, 0.5, 0.75]).unstack()
    norma.columns = ["norma_p25", "norma_mediana", "norma_p75"]
    tabela = tabela.merge(norma, left_on=[chave, "posicao_no_ano"], right_index=True, how="left")
    tabela["desvio_norma"] = tabela["variacao_periodo"] - tabela["norma_mediana"]
    return tabela.drop(columns="posicao_no_ano")


def acrescentar_contribuicao_anual(tabela, periodos_no_ano):
    """Quanto cada componente contribuiu para a inflação anual do INPC geral (pp)."""
    # somar as incidências dos últimos 12 meses é uma aproximação: cada incidência usa os preços
    # relativos do seu próprio mês, então a soma não fecha exatamente com a variação em 12 meses
    # (fica de fora o efeito composto); reescalamos as partes de cada nível para fecharem com o INPC
    soma = tabela.groupby("componente")["incidencia_periodo"].transform(lambda serie: serie.rolling(periodos_no_ano).sum())
    total_do_nivel = soma.groupby([tabela["periodo"], tabela["nivel"]]).transform("sum")
    inflacao_anual = tabela[tabela["componente"] == "indice_general"].set_index("periodo")["variacao_anual"]
    tabela["contribuicao_anual"] = soma * tabela["periodo"].map(inflacao_anual) / total_do_nivel
    tabela.loc[tabela["nivel"] == 0, "contribuicao_anual"] = tabela["variacao_anual"]
    return tabela


def acrescentar_ritmo_dessazonalizado(tabela, dessazonalizadas):
    """Variação mensal dessazonalizada e o SAAR de 3 e 6 meses (só no mensal)."""
    # o SAAR é o ritmo recente da inflação sem sazonalidade, expresso como se durasse um ano inteiro
    sa = dessazonalizadas.sort_values(["componente", "data"]).copy()
    anterior = sa.groupby("componente")["indice_sa"]
    sa["variacao_sa_mensal"] = (sa["indice_sa"] / anterior.shift(1) - 1) * 100
    for meses in (3, 6):
        sa[f"saar_{meses}m"] = ((sa["indice_sa"] / anterior.shift(meses)) ** (12 / meses) - 1) * 100
    colunas = ["componente", "periodo", "variacao_sa_mensal", "saar_3m", "saar_6m"]
    return tabela.merge(sa[colunas], on=["componente", "periodo"], how="left")


def metricas_componentes(series, dessazonalizadas):
    """Tabela (componente, frequência, período) com variações, incidência, contribuição anual, norma e SAAR."""
    tabelas = []
    for frequencia, periodos_no_ano in PERIODOS_POR_ANO.items():
        da_frequencia = series[series["frequencia"] == frequencia]
        indices = da_frequencia[da_frequencia["tipo"] == "indice"].rename(columns={"valor": "indice"})
        incidencias = da_frequencia[da_frequencia["tipo"] == "incidencia"][["componente", "periodo", "valor"]]
        tabela = indices.merge(incidencias.rename(columns={"valor": "incidencia_periodo"}), on=["componente", "periodo"], how="left")
        tabela = acrescentar_variacoes(tabela.sort_values(["componente", "data"]), "componente", periodos_no_ano)
        tabelas.append(acrescentar_norma(acrescentar_contribuicao_anual(tabela, periodos_no_ano), "componente"))
    tabela = acrescentar_ritmo_dessazonalizado(pd.concat(tabelas), dessazonalizadas)
    return tabela[["componente", "nivel", "pai", "frequencia", "periodo", "rotulo_periodo", "rotulo_curto", "rotulo_mes", "data", "indice", "variacao_periodo", "variacao_anual",
                   "incidencia_periodo", "contribuicao_anual", "norma_mediana", "norma_p25", "norma_p75", "desvio_norma",
                   "variacao_sa_mensal", "saar_3m", "saar_6m"]]


# ==== 2. Genéricos ====
def peso_efetivo_do_generico(tabela, pesos, inpc, frequencia):
    """Quantos pp do INPC cada 1% de variação do genérico gera no período, com os pesos da cesta 2024."""
    # na cesta 2024 o INPC é a média ponderada dos índices dos genéricos, cada um dividido pelo seu fator
    # de encadeamento (índice da 2Q jul/2024 / 100); o peso efetivo é o peso da cesta corrigido pelo quanto
    # o preço do genérico subiu em relação ao INPC desde a troca de cesta (o INEGI chama de preço relativo)
    relativo = tabela["indice"] / tabela["codigo_generico"].map(pesos["fator_encadeamento"])
    periodo_anterior = tabela.groupby("codigo_generico")["periodo"].shift(1)
    inpc_anterior = periodo_anterior.map(inpc[frequencia]) / (inpc["quinzenal"]["2024-07-Q2"] / 100)
    relativo_anterior = relativo.groupby(tabela["codigo_generico"]).shift(1)
    peso = tabela["codigo_generico"].map(pesos["ponderador"]) * relativo_anterior / inpc_anterior / 100
    return peso.where(periodo_anterior.fillna("") >= p.INICIO_CESTA_2024[frequencia])


def metricas_genericos(genericos, ponderadores, series):
    """Tabela (genérico, frequência, período): variações, norma, incidência e contribuição da surpresa."""
    pesos = ponderadores[ponderadores["cesta"] == "2024"].set_index("codigo_generico")
    geral = series[(series["tipo"] == "indice") & (series["componente"] == "indice_general")]
    inpc = {frequencia: tabela.set_index("periodo")["valor"] for frequencia, tabela in geral.groupby("frequencia")}
    tabelas = []
    for frequencia, periodos_no_ano in PERIODOS_POR_ANO.items():
        tabela = genericos[genericos["frequencia"] == frequencia].sort_values(["codigo_generico", "data"]).copy()
        tabela = acrescentar_variacoes(tabela, "codigo_generico", periodos_no_ano)
        tabela["peso_efetivo"] = peso_efetivo_do_generico(tabela, pesos, inpc, frequencia)
        tabela["incidencia_periodo"] = tabela["peso_efetivo"] * tabela["variacao_periodo"]
        tabela = acrescentar_norma(tabela, "codigo_generico")
        # o desvio em % favorece itens voláteis (frutas e verduras); multiplicado pelo peso efetivo,
        # vira quantos pp do INPC vieram do movimento anormal, que é o que interessa ao analista
        tabela["contribuicao_surpresa"] = tabela["peso_efetivo"] * tabela["desvio_norma"]
        tabelas.append(tabela)
    return pd.concat(tabelas)[["codigo_generico", "nome_generico", "subindice", "frequencia", "periodo", "rotulo_periodo", "data", "indice",
                               "variacao_periodo", "variacao_anual", "norma_mediana", "desvio_norma", "incidencia_periodo",
                               "contribuicao_surpresa"]]


def serie_difusao(genericos, ponderadores):
    """Mês a mês: % dos genéricos e da cesta em alta, e % da cesta com inflação anual acima de 3% e de 4%."""
    # a difusão mostra se a inflação está espalhada ou concentrada em poucos itens; 3% é a meta do Banxico
    # e 4% o teto do intervalo. Cada mês usa os pesos da cesta vigente, renormalizados aos genéricos com dado
    mensal = genericos[(genericos["frequencia"] == "mensal") & (genericos["data"].dt.year >= p.ANO_INICIO_GRAFICOS)].copy()
    cesta = mensal["periodo"].ge(p.INICIO_CESTA_2024["mensal"]).map({True: "2024", False: "2018"})
    pesos = ponderadores.dropna(subset=["codigo_generico"]).set_index(["cesta", "codigo_generico"])["ponderador"]
    mensal["peso"] = pesos.reindex(list(zip(cesta, mensal["codigo_generico"]))).values
    mensal = mensal.dropna(subset=["peso", "variacao_periodo"])
    por_mes = mensal.groupby("periodo")

    def pct_da_cesta(condicao):
        """Parte do peso da cesta, em %, dos genéricos que cumprem a condição."""
        return mensal["peso"].where(condicao, 0).groupby(mensal["periodo"]).sum() / por_mes["peso"].sum() * 100

    return pd.DataFrame({"data": por_mes["data"].first(), "rotulo_periodo": por_mes["rotulo_periodo"].first(),
                         "pct_genericos_em_alta": (mensal["variacao_periodo"] > 0).groupby(mensal["periodo"]).mean() * 100,
                         "pct_cesta_em_alta": pct_da_cesta(mensal["variacao_periodo"] > 0),
                         "pct_cesta_anual_acima_3": pct_da_cesta(mensal["variacao_anual"] > 3),
                         "pct_cesta_anual_acima_4": pct_da_cesta(mensal["variacao_anual"] > 4)}).reset_index()


# ==== 3. Resumo do último release ====
def arredondar(valor):
    """Número com 4 casas para o JSON do dashboard."""
    return round(float(valor), 4)


def numeros_principais(componentes, frequencia):
    """INPC, subyacente e no subyacente: variação no período, anual e quanto a anual mudou contra o período anterior."""
    resumo = {}
    for componente in PRINCIPAIS:
        serie = componentes[(componentes["componente"] == componente) & (componentes["frequencia"] == frequencia)].sort_values("data")
        atual, anterior = serie.iloc[-1], serie.iloc[-2]
        resumo[componente] = {"periodo": atual["periodo"], "rotulo_periodo": atual["rotulo_periodo"], "rotulo_anterior": anterior["rotulo_periodo"],
                              "variacao_periodo": arredondar(atual["variacao_periodo"]),
                              "variacao_anual": arredondar(atual["variacao_anual"]),
                              "mudanca_da_anual_pp": arredondar(atual["variacao_anual"] - anterior["variacao_anual"])}
    return resumo


def mensal_implicito(componentes, mes):
    """Variação mensal e anual implícitas do mês corrente, no dia em que só a 1a quinzena foi publicada."""
    # o índice mensal é a média das duas quinzenas, então no dia da 1a quinzena três quartos da informação
    # do mês já são conhecidos; a 2a quinzena é estimada aplicando à 1a a variação histórica típica
    # daquela 2a quinzena (mediana de 2010-2019), com o intervalo dado pelos quartis
    quinzenal = componentes[componentes["frequencia"] == "quinzenal"]
    mensal = componentes[componentes["frequencia"] == "mensal"].set_index(["componente", "periodo"])["indice"]
    mes_anterior, mes_do_ano_anterior = str(pd.Period(mes) - 1), str(pd.Period(mes) - 12)
    resultado = {"mes": mes, "rotulo_mes": quinzenal[quinzenal["periodo"] == f"{mes}-Q1"]["rotulo_mes"].iloc[0]}
    for componente in ("indice_general", "subyacente"):
        da_serie = quinzenal[quinzenal["componente"] == componente].set_index("periodo")
        primeira = da_serie.loc[f"{mes}-Q1", "indice"]
        norma = da_serie[da_serie.index.str.endswith(f"{mes[5:]}-Q2")].iloc[-1]  # a norma é a mesma em todos os anos
        resultado[componente] = {}
        for cenario, coluna in (("p25", "norma_p25"), ("mediana", "norma_mediana"), ("p75", "norma_p75")):
            indice_do_mes = (primeira + primeira * (1 + norma[coluna] / 100)) / 2
            resultado[componente][cenario] = {
                "variacao_mensal": arredondar((indice_do_mes / mensal[(componente, mes_anterior)] - 1) * 100),
                "variacao_anual": arredondar((indice_do_mes / mensal[(componente, mes_do_ano_anterior)] - 1) * 100)}
    return resultado


def registros(tabela):
    """Linhas de genéricos como lista de dicionários para o JSON."""
    colunas = ["codigo_generico", "nome_generico", "subindice", "variacao_periodo", "norma_mediana", "desvio_norma",
               "incidencia_periodo", "contribuicao_surpresa"]
    return tabela[colunas].round(4).to_dict("records")


def destaques(genericos, frequencia):
    """Os 5 genéricos que mais puxaram a inflação para cima e para baixo, e os 5 de maior surpresa em pp do INPC."""
    da_frequencia = genericos[genericos["frequencia"] == frequencia]
    ultimo = da_frequencia[da_frequencia["periodo"] == da_frequencia["periodo"].max()]
    return {"frequencia": frequencia, "periodo": ultimo["periodo"].iloc[0], "rotulo_periodo": ultimo["rotulo_periodo"].iloc[0],
            "maiores_incidencias": registros(ultimo.nlargest(5, "incidencia_periodo")),
            "menores_incidencias": registros(ultimo.nsmallest(5, "incidencia_periodo")),
            "acima_da_norma": registros(ultimo.nlargest(5, "contribuicao_surpresa")),
            "abaixo_da_norma": registros(ultimo.nsmallest(5, "contribuicao_surpresa"))}


if __name__ == "__main__":
    inicio = time.time()
    series, ponderadores = ler("series"), ler("ponderadores")
    componentes = metricas_componentes(series, ler("series_dessazonalizadas"))
    genericos = metricas_genericos(ler("genericos"), ponderadores, series)
    difusao = serie_difusao(genericos, ponderadores)
    recentes = genericos.groupby("frequencia")["data"].transform("max") - pd.DateOffset(months=24) < genericos["data"]
    componentes.to_parquet(p.PASTA_PROCESSED / "metricas_componentes.parquet", index=False)
    genericos[recentes].to_parquet(p.PASTA_PROCESSED / "metricas_genericos.parquet", index=False)
    difusao.to_parquet(p.PASTA_PROCESSED / "metricas_difusao.parquet", index=False)

    ultimo = componentes.groupby("frequencia")["periodo"].max().to_dict()
    tipo = "1a_quinzena" if ultimo["quinzenal"].endswith("Q1") else "mensal_e_2a_quinzena"
    rotulos = componentes[componentes["periodo"].isin(ultimo.values())].groupby("frequencia")["rotulo_periodo"].first().to_dict()
    resumo = {"ultimo_periodo": ultimo, "ultimo_rotulo": rotulos, "tipo_ultimo_release": tipo,
              "principais": {frequencia: numeros_principais(componentes, frequencia) for frequencia in PERIODOS_POR_ANO},
              "mensal_implicito": mensal_implicito(componentes, ultimo["quinzenal"][:7]) if tipo == "1a_quinzena" else None,
              "difusao": {coluna: (valor if coluna in ("periodo", "rotulo_periodo") else arredondar(valor)) for coluna, valor in
                          difusao.drop(columns="data").iloc[-1].items()},
              "destaques": destaques(genericos, "quinzenal" if tipo == "1a_quinzena" else "mensal")}
    (p.PASTA_PROCESSED / "metricas_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Métricas: componentes {len(componentes)}, genéricos {int(recentes.sum())}, difusão {len(difusao)} linhas; último release {tipo}; {time.time() - inicio:.1f} s")
