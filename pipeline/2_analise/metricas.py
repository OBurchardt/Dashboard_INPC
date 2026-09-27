# Etapa 2.1: Métricas
# Aqui estão as contas que eu faço no dia do release, já em cima da base validada. Para os 16
# componentes: variação no período e em 12 meses, incidência, contribuição para a inflação anual,
# comparação com o "normal" daquele mês (norma sazonal de 2010 a 2019) e o ritmo dessazonalizado
# anualizado. Para os 292 genéricos, as mesmas leituras e a incidência de cada um. No fim monto um
# resumo com o que vai no topo do dashboard: os números principais, o mensal implícito no dia da
# 1a quinzena, a difusão e os genéricos que mais pesaram.

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p


# ==== 1. Variações, norma sazonal e contribuições ====
def ler(nome):
    """Uma tabela de data/processed."""
    return pd.read_parquet(p.PASTA_PROCESSED / f"{nome}.parquet")


def acrescentar_variacoes(tabela, chave, periodos_no_ano):
    """Variação contra o período anterior e contra um ano antes, série a série; a tabela tem de estar em ordem de data."""
    # no quinzenal "período anterior" é a quinzena de antes, não o mês; e um ano são 24 quinzenas
    anterior = tabela.groupby(chave)["indice"]
    tabela["variacao_periodo"] = (tabela["indice"] / anterior.shift(1) - 1) * 100
    tabela["variacao_anual"] = (tabela["indice"] / anterior.shift(periodos_no_ano) - 1) * 100
    return tabela


def acrescentar_norma(tabela, chave):
    """Quanto aquele mês (ou quinzena) costuma subir: mediana e quartis de 2010 a 2019, e o quanto o dado de agora se afasta disso."""
    # uso a mediana e não a média porque a janela tem choques que puxariam a média, como a liberalização da gasolina em jan/2017
    tabela["posicao_no_ano"] = tabela["periodo"].str[5:]  # "08" no mensal, "08-Q1" no quinzenal
    inicio, fim = p.ANOS_NORMA_SAZONAL
    janela = tabela[tabela["data"].dt.year.between(inicio, fim)]
    norma = janela.groupby([chave, "posicao_no_ano"])["variacao_periodo"].quantile([0.25, 0.5, 0.75]).unstack()
    norma.columns = ["norma_p25", "norma_mediana", "norma_p75"]
    tabela = tabela.merge(norma, left_on=[chave, "posicao_no_ano"], right_index=True, how="left")
    tabela["desvio_norma"] = tabela["variacao_periodo"] - tabela["norma_mediana"]
    return tabela.drop(columns="posicao_no_ano")


def contribuicao_em_12_meses(incidencias, inpc, periodos_no_ano):
    """Contribuição para a inflação em 12 meses de cada coluna de incidências (posição x série), dado o INPC na mesma grade."""
    soma = incidencias.mul(inpc.shift(1), axis=0).rolling(periodos_no_ano).sum()  # o rolling exige os h valores presentes
    return soma.div(inpc.shift(periodos_no_ano), axis=0)


def acrescentar_contribuicao_anual(tabela, periodos_no_ano):
    """Quantos pontos da inflação em 12 meses vieram de cada componente, pela identidade exata do encadeamento."""
    # a incidência c(s) são pontos da variação do INPC no período s, medidos sobre o nível I(s-1) do INPC geral.
    # Para somar pontos de períodos diferentes, levo todos para a mesma base I(t-h):
    # C(t) = soma de c(s) x I(s-1) / I(t-h), com s de t-h+1 até t (h = 12 meses ou 24 quinzenas).
    # Somando os componentes de um nível, isso dá a variação anual do INPC; o que sobra é o arredondamento das
    # incidências publicadas, e não reescalo nada. Só calculo com a janela inteira: faltou incidência ou período, fica nulo
    grade = range(tabela["posicao"].min(), tabela["posicao"].max() + 1)  # a grade de posições acusa período ausente
    inpc = tabela[tabela["componente"] == "indice_general"].set_index("posicao")["indice"].reindex(grade)
    incidencias = tabela.pivot(index="posicao", columns="componente", values="incidencia_periodo").reindex(grade)
    contribuicao = contribuicao_em_12_meses(incidencias, inpc, periodos_no_ano).stack(future_stack=True).rename("contribuicao_anual")
    return tabela.merge(contribuicao, left_on=["posicao", "componente"], right_index=True, how="left")


def contribuicao_na_base(tabela, coluna_base):
    """Contribuição de cada componente para a variação em 12 meses do componente indicado em coluna_base (pp)."""
    # a contribuição anual está na base do INPC; multiplicar pela variação anual do pai e dividir pela soma das
    # contribuições dos irmãos (mesmo pai, mesmo nível) leva para a base do pai. Com cesta fixa a conta é exata:
    # ex.: habitação 1,63 + educação 0,39 + outros 2,32 = serviços 4,34. Divido pelos irmãos e não pela contribuição
    # publicada do pai porque o arredondamento das incidências (até 0,004 pp) é ampliado quando o pai quase não varia:
    # agropecuários a 0,17% em jul/2025 deixava os filhos 0,035 pp longe do pai; assim eles somam o pai exatamente
    variacoes = tabela[["componente", "periodo", "variacao_anual"]].rename(columns={"componente": coluna_base, "variacao_anual": "variacao_base"})
    variacao_base = tabela[[coluna_base, "periodo"]].merge(variacoes, on=[coluna_base, "periodo"], how="left")["variacao_base"].values
    soma_dos_irmaos = tabela.groupby([coluna_base, "periodo", "nivel"], dropna=False)["contribuicao_anual"].transform("sum").values
    return tabela["contribuicao_anual"].values * variacao_base / soma_dos_irmaos


def grupo_de_nivel_1(componente, pais):
    """Sobe a árvore até o filho direto do INPC (núcleo ou não núcleo); o próprio INPC não tem grupo."""
    while pais.get(componente) not in ("indice_general", None):
        componente = pais[componente]
    return componente if pais.get(componente) == "indice_general" else None


def acrescentar_contribuicao_no_pai(tabela):
    """Contribuição para a variação em 12 meses do pai, e do grupo de nível 1 (núcleo ou não núcleo) acima dele."""
    # o grupo serve ao gráfico do não núcleo desde o mês-base, que junta os quatro subíndices numa conta só
    pais = tabela.drop_duplicates("componente").set_index("componente")["pai"].to_dict()
    tabela["grupo"] = tabela["componente"].map(lambda componente: grupo_de_nivel_1(componente, pais))
    tabela["contribuicao_no_pai"] = contribuicao_na_base(tabela, "pai")
    tabela["contribuicao_no_grupo"] = contribuicao_na_base(tabela, "grupo")
    return tabela.drop(columns="grupo")


def conferir_contribuicao_no_pai(componentes, meses):
    """Para o pipeline se, em algum período recente, os filhos não somarem a variação em 12 meses do pai."""
    # serve aos componentes e às aberturas dos subíndices; período sem contribuição nenhuma não entra na conta
    for frequencia, periodos_no_ano in p.PERIODOS_POR_ANO.items():
        tabela = componentes[componentes["frequencia"] == frequencia]
        recentes = tabela[tabela["posicao"] > tabela["posicao"].max() - meses * periodos_no_ano // 12]
        soma = recentes.dropna(subset=["pai"]).groupby(["pai", "periodo"])["contribuicao_no_pai"].sum(min_count=1)
        pais = recentes[recentes["componente"].isin(soma.index.get_level_values("pai"))]
        pai = pais.set_index(["componente", "periodo"])["variacao_anual"].reindex(soma.index)
        diferenca = (soma - pai).abs()
        if diferenca.max() > p.TOLERANCIA_VALIDACAO_PP:
            componente, periodo = diferenca.idxmax()
            raise ValueError(f"Contribuição no pai não fecha: {componente} em {periodo} ({frequencia}), diferença de {diferenca.max():.4f} pp")


def residuo_da_contribuicao_anual(componentes, meses):
    """O quanto as contribuições de cada nível deixam de fechar com o INPC em 12 meses, no pior período da janela."""
    # é a prova da identidade: sem reescala, o que sobra tem de ser só arredondamento
    residuos = []
    for frequencia, periodos_no_ano in p.PERIODOS_POR_ANO.items():
        tabela = componentes[componentes["frequencia"] == frequencia]
        recentes = tabela[tabela["posicao"] > tabela["posicao"].max() - meses * periodos_no_ano // 12]
        soma = recentes[recentes["nivel"] > 0].groupby(["periodo", "nivel"])["contribuicao_anual"].sum(min_count=1)
        inpc = recentes[recentes["nivel"] == 0].set_index("periodo")["variacao_anual"]
        residuos.append((soma - soma.index.get_level_values("periodo").map(inpc)).abs().max())
    return max(residuos)


def acrescentar_ritmo_dessazonalizado(tabela, dessazonalizadas):
    """Variação mensal sem sazonalidade e o SAAR de 3 e 6 meses; só existe no mensal."""
    # o SAAR pega a alta dos últimos 3 (ou 6) meses já sem sazonalidade e mostra quanto daria se durasse um ano:
    # ((índice hoje / índice 3 meses atrás) elevado a 12/3, menos 1). Se ele está abaixo da anual, a anual tende a cair
    sa = dessazonalizadas.sort_values(["componente", "data"]).copy()
    anterior = sa.groupby("componente")["indice_sa"]
    sa["variacao_sa_mensal"] = (sa["indice_sa"] / anterior.shift(1) - 1) * 100
    for meses in (3, 6):
        sa[f"saar_{meses}m"] = ((sa["indice_sa"] / anterior.shift(meses)) ** (12 / meses) - 1) * 100
    colunas = ["componente", "periodo", "variacao_sa_mensal", "saar_3m", "saar_6m"]
    return tabela.merge(sa[colunas], on=["componente", "periodo"], how="left")


def metricas_componentes(series, dessazonalizadas):
    """Uma linha por componente, frequência e período, com tudo o que o dashboard mostra dos componentes."""
    tabelas = []
    for frequencia, periodos_no_ano in p.PERIODOS_POR_ANO.items():
        da_frequencia = series[series["frequencia"] == frequencia]
        indices = da_frequencia[da_frequencia["tipo"] == "indice"].rename(columns={"valor": "indice"})
        incidencias = da_frequencia[da_frequencia["tipo"] == "incidencia"][["componente", "periodo", "valor"]]
        tabela = indices.merge(incidencias.rename(columns={"valor": "incidencia_periodo"}), on=["componente", "periodo"], how="left")
        tabela = acrescentar_variacoes(tabela.sort_values(["componente", "data"]), "componente", periodos_no_ano)
        tabela = acrescentar_contribuicao_no_pai(acrescentar_contribuicao_anual(tabela, periodos_no_ano))
        tabelas.append(acrescentar_norma(tabela, "componente"))
    tabela = acrescentar_ritmo_dessazonalizado(pd.concat(tabelas), dessazonalizadas)
    return tabela[["componente", "nivel", "pai", "frequencia", "periodo", "posicao", "rotulo_periodo", "rotulo_curto", "rotulo_mes", "data", "indice", "variacao_periodo", "variacao_anual",
                   "incidencia_periodo", "contribuicao_anual", "contribuicao_no_pai", "contribuicao_no_grupo", "norma_mediana", "norma_p25", "norma_p75", "desvio_norma",
                   "variacao_sa_mensal", "saar_3m", "saar_6m"]]


# ==== 2. Genéricos ====
def peso_efetivo_do_generico(tabela, pesos, inpc, frequencia):
    """Quantos pontos do INPC cada 1% de alta do genérico gera neste período."""
    # na cesta 2024 o INPC é a média ponderada dos genéricos, cada índice dividido pelo seu fator de encadeamento
    # (o índice da 2Q jul/2024 dividido por 100). O peso efetivo é o peso da cesta vezes o quanto o genérico subiu
    # em relação ao INPC desde então: peso x (índice relativo do genérico no período anterior / INPC relativo no período anterior).
    # Cuidado: não é o peso da planilha; um item que subiu mais que a média passa a pesar mais
    relativo = tabela["indice"] / tabela["codigo_generico"].map(pesos["fator_encadeamento"])
    periodo_anterior = tabela.groupby("codigo_generico")["periodo"].shift(1)
    inpc_anterior = periodo_anterior.map(inpc[frequencia]) / (inpc["quinzenal"]["2024-07-Q2"] / 100)
    relativo_anterior = relativo.groupby(tabela["codigo_generico"]).shift(1)
    peso = tabela["codigo_generico"].map(pesos["ponderador"]) * relativo_anterior / inpc_anterior / 100
    # antes da cesta 2024 os pesos eram outros, então lá eu não calculo
    return peso.where(periodo_anterior.fillna("") >= p.INICIO_CESTA_2024[frequencia])


def metricas_genericos(genericos, ponderadores, series):
    """Uma linha por genérico, frequência e período: variações, norma, incidência e o desvio sazonal ponderado."""
    pesos = ponderadores[ponderadores["cesta"] == "2024"].set_index("codigo_generico")
    geral = series[(series["tipo"] == "indice") & (series["componente"] == "indice_general")]
    inpc = {frequencia: tabela.set_index("periodo")["valor"] for frequencia, tabela in geral.groupby("frequencia")}
    tabelas = []
    for frequencia, periodos_no_ano in p.PERIODOS_POR_ANO.items():
        tabela = genericos[genericos["frequencia"] == frequencia].sort_values(["codigo_generico", "data"]).copy()
        tabela = acrescentar_variacoes(tabela, "codigo_generico", periodos_no_ano)
        tabela["peso_efetivo"] = peso_efetivo_do_generico(tabela, pesos, inpc, frequencia)
        tabela["incidencia_periodo"] = tabela["peso_efetivo"] * tabela["variacao_periodo"]
        tabela = acrescentar_norma(tabela, "codigo_generico")
        # o desvio em % sempre põe frutas e verduras no topo, porque elas oscilam muito; multiplicado pelo peso efetivo
        # ele vira o desvio sazonal ponderado: quantos pontos do INPC vieram do movimento fora da mediana de 2010 a 2019.
        # Não é surpresa contra expectativa de mercado, e as medianas dos itens não somam a mediana do INPC
        tabela["desvio_sazonal_ponderado"] = tabela["peso_efetivo"] * tabela["desvio_norma"]
        tabelas.append(tabela)
    return pd.concat(tabelas)[["codigo_generico", "nome_generico", "subindice", "frequencia", "periodo", "posicao", "rotulo_periodo", "data", "indice",
                               "variacao_periodo", "variacao_anual", "norma_mediana", "desvio_norma", "incidencia_periodo",
                               "desvio_sazonal_ponderado"]]


def serie_difusao(genericos, ponderadores):
    """Mês a mês, quão espalhada está a inflação: quanto da cesta subiu no mês e quanto está acima de 3% e de 4% em 12 meses."""
    # 3% e 4% são a meta do Banxico para o INPC e o teto do intervalo de tolerância; aqui são só uma régua, porque
    # item nenhum tem meta própria. Cada mês usa os pesos da cesta que valia na época. Cada medida conta só os itens
    # que têm o dado que ela usa (variação no mês, ou variação em 12 meses) e divide pelo peso desses itens; a
    # cobertura diz quanto do peso total da cesta esses itens somam, para ninguém ler 60% de 80% como 60% de tudo
    mensal = genericos[(genericos["frequencia"] == "mensal") & (genericos["data"].dt.year >= p.ANO_INICIO_GRAFICOS)].copy()
    mensal["cesta"] = mensal["periodo"].ge(p.INICIO_CESTA_2024["mensal"]).map({True: "2024", False: "2018"})
    pesos = ponderadores.dropna(subset=["codigo_generico"]).set_index(["cesta", "codigo_generico"])["ponderador"]
    mensal["peso"] = pesos.reindex(list(zip(mensal["cesta"], mensal["codigo_generico"]))).values
    mensal = mensal.dropna(subset=["peso"])
    peso_total = mensal.groupby("periodo")["cesta"].first().map(ponderadores.groupby("cesta")["ponderador"].sum())
    por_mes = mensal.groupby("periodo")

    def medida(coluna, condicao):
        """Parte do peso válido que cumpre a condição, número de itens válidos e cobertura do peso total da cesta."""
        valido = mensal[coluna].notna()
        peso_valido = mensal["peso"].where(valido, 0).groupby(mensal["periodo"]).sum()
        return (mensal["peso"].where(valido & condicao, 0).groupby(mensal["periodo"]).sum() / peso_valido * 100,
                valido.groupby(mensal["periodo"]).sum(), peso_valido / peso_total * 100)

    em_alta, itens_mes, cobertura_mes = medida("variacao_periodo", mensal["variacao_periodo"] > 0)
    acima_3, itens_anual, cobertura_anual = medida("variacao_anual", mensal["variacao_anual"] > 3)
    acima_4 = medida("variacao_anual", mensal["variacao_anual"] > 4)[0]
    return pd.DataFrame({"data": por_mes["data"].first(), "rotulo_periodo": por_mes["rotulo_periodo"].first(),
                         "pct_genericos_em_alta": (mensal["variacao_periodo"] > 0).groupby(mensal["periodo"]).sum() / itens_mes * 100,
                         "pct_cesta_em_alta": em_alta, "pct_cesta_anual_acima_3": acima_3, "pct_cesta_anual_acima_4": acima_4,
                         "itens_validos_mes": itens_mes, "cobertura_peso_mes": cobertura_mes,
                         "itens_validos_anual": itens_anual, "cobertura_peso_anual": cobertura_anual}).reset_index()


# ==== 3. Aberturas dos subíndices ====
def acrescentar_contribuicao_anual_dos_genericos(genericos, componentes):
    """A contribuição de cada genérico para a inflação em 12 meses, pela mesma identidade dos componentes."""
    # a incidência dos genéricos só existe na cesta 2024, então a contribuição em 12 meses começa 12 meses depois
    partes = []
    for frequencia, periodos_no_ano in p.PERIODOS_POR_ANO.items():
        tabela = genericos[genericos["frequencia"] == frequencia]
        grade = range(tabela["posicao"].min(), tabela["posicao"].max() + 1)
        geral = componentes[(componentes["componente"] == "indice_general") & (componentes["frequencia"] == frequencia)]
        inpc = geral.set_index("posicao")["indice"].reindex(grade)
        incidencias = tabela.pivot(index="posicao", columns="codigo_generico", values="incidencia_periodo").reindex(grade)
        contribuicao = contribuicao_em_12_meses(incidencias, inpc, periodos_no_ano).stack(future_stack=True).rename("contribuicao_anual")
        partes.append(tabela.merge(contribuicao, left_on=["posicao", "codigo_generico"], right_index=True, how="left"))
    return pd.concat(partes)


def aberturas_dos_subindices(genericos, componentes, ponderadores):
    """Para cada subíndice, as 6 aberturas de maior peso na cesta 2024 e as demais, com a contribuição para a variação em 12 meses dele."""
    # a chave da abertura é a posição dela no subíndice (abertura_1 é a de maior peso), porque o dashboard pinta pela posição.
    # A troca de base é a mesma dos componentes: dividir pela soma das contribuições dos irmãos, que aqui são todos os
    # genéricos do subíndice. "Demais" é o subíndice menos a soma das 6; quem tem 6 genéricos ou menos não tem "Demais"
    pesos = ponderadores[ponderadores["cesta"] == "2024"].dropna(subset=["codigo_generico"])
    maiores = pesos.sort_values("ponderador", ascending=False).groupby("subindice").head(6)
    chave = dict(zip(maiores["codigo_generico"], "abertura_" + (maiores.groupby("subindice").cumcount() + 1).astype(str)))
    tabela = acrescentar_contribuicao_anual_dos_genericos(genericos, componentes)
    subindices = componentes[["componente", "frequencia", "periodo", "variacao_anual"]].rename(columns={"componente": "subindice", "variacao_anual": "variacao_subindice"})
    tabela = tabela.merge(subindices, on=["subindice", "frequencia", "periodo"], how="left")
    soma_do_subindice = tabela.groupby(["subindice", "frequencia", "periodo"])["contribuicao_anual"].transform("sum")
    tabela["contribuicao_no_pai"] = tabela["contribuicao_anual"] * tabela["variacao_subindice"] / soma_do_subindice
    tabela["componente"] = tabela["codigo_generico"].map(chave)
    principais = tabela.dropna(subset=["componente"]).rename(columns={"subindice": "pai", "nome_generico": "nome"})
    soma_das_6 = principais.groupby(["pai", "frequencia", "periodo"])["contribuicao_no_pai"].sum(min_count=1).rename("soma_das_6")
    com_demais = pesos.groupby("subindice").size().loc[lambda n: n > 6].index
    demais = componentes[componentes["componente"].isin(com_demais)].drop(columns="pai").rename(columns={"componente": "pai"})
    demais = demais.merge(soma_das_6, left_on=["pai", "frequencia", "periodo"], right_index=True, how="left")
    demais = demais.assign(componente="demais", nome="Demais", contribuicao_no_pai=demais["variacao_anual"] - demais["soma_das_6"], variacao_anual=float("nan"))
    colunas = ["pai", "componente", "nome", "frequencia", "periodo", "posicao", "rotulo_periodo", "data", "variacao_anual", "contribuicao_no_pai"]
    aberturas = pd.concat([principais[colunas], demais[colunas]])
    return aberturas[aberturas["data"].dt.year >= p.ANO_INICIO_GRAFICOS]


# ==== 4. Resumo do último release ====
def arredondar(valor):
    """Guardo 6 casas no JSON e deixo o arredondamento para a tela; arredondar duas vezes já me fez errar o último dígito."""
    return round(float(valor), 6)


def numeros_principais(componentes, frequencia):
    """INPC, subyacente e no subyacente: variação no período, em 12 meses e quanto a de 12 meses mudou desde o período anterior."""
    resumo = {}
    for componente in p.COMPONENTES_PRINCIPAIS:
        serie = componentes[(componentes["componente"] == componente) & (componentes["frequencia"] == frequencia)].sort_values("data")
        atual, anterior = serie.iloc[-1], serie.iloc[-2]
        resumo[componente] = {"periodo": atual["periodo"], "rotulo_periodo": atual["rotulo_periodo"], "rotulo_anterior": anterior["rotulo_periodo"],
                              "variacao_periodo": arredondar(atual["variacao_periodo"]),
                              "variacao_anual": arredondar(atual["variacao_anual"]),
                              "mudanca_da_anual_pp": arredondar(atual["variacao_anual"] - anterior["variacao_anual"])}
    return resumo


def variacao_estimada(primeira, alta_da_segunda, indice_anterior):
    """A variação do mês estimado sobre o mês anterior, dada a 1a quinzena e quanto a 2a sobe sobre ela (%)."""
    # o índice mensal é a média das duas quinzenas, não a soma das variações:
    # índice do mês = (1a quinzena + 1a quinzena x (1 + alta da 2a)) / 2
    return ((primeira + primeira * (1 + alta_da_segunda / 100)) / 2 / indice_anterior - 1) * 100


def erros_do_mensal_implicito(quinzenal, mensal, mes):
    """Realizado menos estimado, em pp da variação mensal, para cada mês de 2020 até o anterior ao de agora."""
    # a mediana da 2a quinzena vem de 2010-2019, então de 2020 em diante a estimativa só usa passado:
    # é o backtest sem informação futura do próprio método que o cartão mostra
    erros = {}
    for periodo in mensal.index:
        anterior = str(pd.Period(periodo) - 1)
        if int(periodo[:4]) > p.ANOS_NORMA_SAZONAL[1] and periodo < mes and anterior in mensal.index:
            estimada = variacao_estimada(quinzenal.at[f"{periodo}-Q1", "indice"], quinzenal.at[f"{periodo}-Q2", "norma_mediana"], mensal[anterior])
            erros[periodo] = (mensal[periodo] / mensal[anterior] - 1) * 100 - estimada
    return pd.Series(erros)


def cobertura_fora_da_amostra(erros, primeiros=24):
    """Em quantos meses o erro caiu entre os quartis 25 e 75 dos erros anteriores a ele (%); perto de 50% é faixa honesta."""
    # os primeiros 24 meses só formam a faixa, porque com poucos erros os quartis ainda não dizem nada
    dentro = [erros.iloc[:i].quantile(0.25) <= erros.iloc[i] <= erros.iloc[:i].quantile(0.75) for i in range(primeiros, len(erros))]
    return sum(dentro) / len(dentro) * 100, len(dentro)


def mensal_implicito(componentes, mes):
    """Minha estimativa do mês fechado no dia em que só a 1a quinzena saiu, com a faixa tirada dos erros do backtest."""
    # no dia da 1a quinzena metade da média já está publicada, e a 2a parte do mesmo nível; o único incerto é quanto
    # ela sobe sobre a 1a. A estimativa central usa a mediana dessa alta em 2010-2019. A faixa não é mais o p25-p75
    # dessa alta, que conteve o mês realizado em só 35% dos casos: é a central mais os quartis 25 e 75 dos erros de
    # previsão da variação mensal, cada série com os seus
    quinzenal = componentes[componentes["frequencia"] == "quinzenal"]
    mensal = componentes[componentes["frequencia"] == "mensal"].set_index(["componente", "periodo"])["indice"]
    mes_anterior, mes_do_ano_anterior = str(pd.Period(mes) - 1), str(pd.Period(mes) - 12)
    resultado = {"mes": mes, "rotulo_mes": quinzenal[quinzenal["periodo"] == f"{mes}-Q1"]["rotulo_mes"].iloc[0]}
    for componente in ("indice_general", "subyacente"):
        da_serie, do_mes = quinzenal[quinzenal["componente"] == componente].set_index("periodo"), mensal.loc[componente]
        mediana = da_serie[da_serie.index.str.endswith(f"{mes[5:]}-Q2")].iloc[-1]["norma_mediana"]  # a mediana é igual em todos os anos
        central = variacao_estimada(da_serie.at[f"{mes}-Q1", "indice"], mediana, do_mes[mes_anterior])
        erros = erros_do_mensal_implicito(da_serie, do_mes, mes)
        cobertura, meses_testados = cobertura_fora_da_amostra(erros)
        resultado[componente] = {"cobertura_da_faixa": arredondar(cobertura), "meses_testados": meses_testados, "meses_de_erro": len(erros)}
        for cenario, ajuste in (("p25", erros.quantile(0.25)), ("mediana", 0), ("p75", erros.quantile(0.75))):
            variacao = central + ajuste
            indice_do_mes = do_mes[mes_anterior] * (1 + variacao / 100)
            resultado[componente][cenario] = {"variacao_mensal": arredondar(variacao),
                                              "variacao_anual": arredondar((indice_do_mes / do_mes[mes_do_ano_anterior] - 1) * 100)}
    return resultado


def registros(tabela):
    """As linhas de genéricos que vão para o JSON."""
    colunas = ["codigo_generico", "nome_generico", "subindice", "variacao_periodo", "norma_mediana", "desvio_norma",
               "incidencia_periodo", "desvio_sazonal_ponderado"]
    return tabela[colunas].round(6).to_dict("records")


def destaques(genericos, frequencia):
    """Os 5 que mais puxaram o índice para cima e para baixo, e os 5 cujo desvio sazonal ponderado mais pesou no INPC."""
    da_frequencia = genericos[genericos["frequencia"] == frequencia]
    ultimo = da_frequencia[da_frequencia["periodo"] == da_frequencia["periodo"].max()]
    return {"frequencia": frequencia, "periodo": ultimo["periodo"].iloc[0], "rotulo_periodo": ultimo["rotulo_periodo"].iloc[0],
            "maiores_incidencias": registros(ultimo.nlargest(5, "incidencia_periodo")),
            "menores_incidencias": registros(ultimo.nsmallest(5, "incidencia_periodo")),
            "acima_da_norma": registros(ultimo.nlargest(5, "desvio_sazonal_ponderado")),
            "abaixo_da_norma": registros(ultimo.nsmallest(5, "desvio_sazonal_ponderado"))}


if __name__ == "__main__":
    inicio = time.time()
    series, ponderadores = ler("series"), ler("ponderadores")
    componentes = metricas_componentes(series, ler("series_dessazonalizadas"))
    genericos = metricas_genericos(ler("genericos"), ponderadores, series)
    difusao = serie_difusao(genericos, ponderadores)
    recentes = genericos.groupby("frequencia")["data"].transform("max") - pd.DateOffset(months=p.MESES_METRICAS_GENERICOS) < genericos["data"]
    componentes.to_parquet(p.PASTA_PROCESSED / "metricas_componentes.parquet", index=False)
    genericos[recentes].to_parquet(p.PASTA_PROCESSED / "metricas_genericos.parquet", index=False)
    difusao.to_parquet(p.PASTA_PROCESSED / "metricas_difusao.parquet", index=False)
    aberturas = aberturas_dos_subindices(genericos, componentes, ponderadores)
    aberturas.to_parquet(p.PASTA_PROCESSED / "metricas_aberturas.parquet", index=False)

    ultimo = componentes.groupby("frequencia")["periodo"].max().to_dict()
    tipo = "1a_quinzena" if ultimo["quinzenal"].endswith("Q1") else "mensal_e_2a_quinzena"
    # num release de 1a quinzena só a quinzena é novidade; nos outros o mês é o dado principal. Decido isso aqui, uma vez,
    # e as etapas seguintes só leem frequencia_do_release
    frequencia_do_release = "quinzenal" if tipo == "1a_quinzena" else "mensal"
    rotulos = componentes[componentes["periodo"].isin(ultimo.values())].groupby("frequencia")["rotulo_periodo"].first().to_dict()
    resumo = {"ultimo_periodo": ultimo, "ultimo_rotulo": rotulos, "tipo_ultimo_release": tipo, "frequencia_do_release": frequencia_do_release,
              "principais": {frequencia: numeros_principais(componentes, frequencia) for frequencia in p.PERIODOS_POR_ANO},
              "mensal_implicito": mensal_implicito(componentes, ultimo["quinzenal"][:7]) if tipo == "1a_quinzena" else None,
              "difusao": {coluna: (valor if coluna in ("periodo", "rotulo_periodo") else arredondar(valor)) for coluna, valor in
                          difusao.drop(columns="data").iloc[-1].items()},
              "destaques": destaques(genericos, frequencia_do_release)}
    (p.PASTA_PROCESSED / "metricas_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    conferir_contribuicao_no_pai(pd.concat([componentes, aberturas]), p.MESES_VALIDACAO_ADITIVIDADE)
    residuo = residuo_da_contribuicao_anual(componentes, p.MESES_VALIDACAO_ADITIVIDADE)
    print(f"Métricas: componentes {len(componentes)}, genéricos {int(recentes.sum())}, difusão {len(difusao)} linhas; último release {tipo}; "
          f"contribuição anual fecha com o INPC a menos de {residuo:.4f} pp nos últimos {p.MESES_VALIDACAO_ADITIVIDADE} meses; {time.time() - inicio:.1f} s")
