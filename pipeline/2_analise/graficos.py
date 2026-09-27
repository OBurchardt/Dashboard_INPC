# Etapa 2.3: Gráficos
# Aqui eu monto as figuras do dashboard com plotly, mas só o conteúdo: os dados, o tipo de
# traço, o nome de cada série e as marcas de referência (a meta de 3% do Banxico e o intervalo de
# 2% a 4%). Cor, fonte e todo o resto do visual ficam no template HTML, que reconhece cada
# componente pelo campo "meta" do traço. Separei assim para poder mudar o visual sem mexer em
# nenhuma conta, e para nada ser calculado aqui: os números vêm prontos das métricas.

import json
import sys
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p

pio.templates.default = "none"  # sem o tema padrão do plotly, que traria cor e fonte e brigaria com o template


# ==== 1. Apoio ====
def ler(nome):
    """Uma tabela de data/processed."""
    return pd.read_parquet(p.PASTA_PROCESSED / f"{nome}.parquet")


def serie(componentes, componente, frequencia="mensal"):
    """Um componente numa frequência, de 2019 para cá, em ordem de data."""
    tabela = componentes[(componentes["componente"] == componente) & (componentes["frequencia"] == frequencia)]
    return tabela[tabela["data"].dt.year >= p.ANO_INICIO_GRAFICOS].sort_values("data")


def linha(tabela, coluna, componente, nome):
    """Uma linha de um componente, com o nome dele em meta para o template saber a cor."""
    return go.Scatter(x=tabela["data"], y=tabela[coluna], mode="lines", name=nome, meta={"componente": componente})


def com_meta(figura):
    """A meta de 3% e o intervalo de tolerância de 2% a 4% do Banxico, como marcas no fundo."""
    figura.add_hrect(y0=2, y1=4, name="banda_meta")
    figura.add_hline(y=3, name="meta")
    return figura


# ==== 2. Visão principal ====
def anual_com_meta(componentes, componente, nome, resumo):
    """A inflação em 12 meses de um componente contra a meta; em release de quinzena, a última quinzena vai como um ponto à parte."""
    # a linha é mensal e o ponto é quinzenal: no dia da 1a quinzena ele é o dado mais novo que existe. Depois de um
    # release mensal o mês já é o dado novo, e a 2a quinzena ao lado dele só confundiria (como nos gráficos de grupos)
    tracos = [linha(serie(componentes, componente), "variacao_anual", componente, nome)]
    subtitulo = "Variação em 12 meses (%)"
    if resumo["frequencia_do_release"] == "quinzenal":
        quinzena = serie(componentes, componente, "quinzenal").iloc[-1]
        tracos.append(go.Scatter(x=[quinzena["data"]], y=[quinzena["variacao_anual"]], mode="markers",
                                 name=f"Última quinzena ({quinzena['rotulo_periodo']})", showlegend=False,
                                 meta={"componente": componente, "destaque": "ultima_quinzena", "rotulo_quinzena": quinzena["rotulo_periodo"]}))
        subtitulo += "; ponto destacado: última quinzena"
    figura = go.Figure(tracos).update_layout(yaxis_title="variação em 12 meses (%)", meta={"subtitulo": subtitulo})
    return com_meta(figura)


def main_inpc_meta(componentes, nomes, resumo):
    """A inflação cheia está dentro da meta do Banxico, e para onde aponta a última quinzena?"""
    return anual_com_meta(componentes, "indice_general", nomes["indice_general"], resumo)


def main_core_meta(componentes, nomes, resumo):
    """O núcleo, que é o que o Banxico olha para decidir juros, está convergindo para 3%?"""
    return anual_com_meta(componentes, "subyacente", nomes["subyacente"], resumo)


def main_vs_norma(componentes, nomes, resumo):
    """O último dado veio acima ou abaixo do que costuma acontecer nessa época do ano?"""
    # barras deitadas para os nomes caberem sem girar; o marcador é a mediana de 2010-2019 daquele mês ou quinzena,
    # e o traço vai do p25 ao p75, então uma barra fora do traço é um dado atípico
    frequencia = resumo["frequencia_do_release"]
    ultimo = componentes[(componentes["frequencia"] == frequencia) & (componentes["periodo"] == resumo["ultimo_periodo"][frequencia])]
    ultimo = ultimo.set_index("componente").loc[[*p.COMPONENTES_PRINCIPAIS, *p.COMPONENTES_NIVEL_2]]
    rotulos = [nomes[c] for c in ultimo.index]
    barras = [go.Bar(y=[nomes[c]], x=[ultimo.at[c, "variacao_periodo"]], orientation="h", name=nomes[c], meta={"componente": c})
              for c in ultimo.index]
    norma = go.Scatter(y=rotulos, x=ultimo["norma_mediana"], mode="markers", name="Padrão sazonal (mediana 2010-2019)", meta={"serie": "norma"},
                       error_x={"type": "data", "symmetric": False, "array": ultimo["norma_p75"] - ultimo["norma_mediana"],
                                "arrayminus": ultimo["norma_mediana"] - ultimo["norma_p25"]})
    figura = go.Figure(barras + [norma])
    # sem inverter, o plotly desenharia a lista de baixo para cima e o INPC ficaria no pé do gráfico
    return figura.update_layout(barmode="overlay", yaxis={"autorange": "reversed"},
                                xaxis_title=f"variação em {resumo['ultimo_rotulo'][frequencia]} (%)")


# ==== 3. Decomposição ====
def decomp_arvore(componentes, nomes, resumo):
    """Do INPC até os subíndices, quanto cada parte puxou a variação do último período?"""
    # a área é o tamanho da incidência dos subíndices, sem sinal, e os níveis de cima somam as áreas dos filhos;
    # o número escrito em cada caixa é a incidência publicada, com sinal
    frequencia = resumo["frequencia_do_release"]
    ultimo = componentes[(componentes["frequencia"] == frequencia) & (componentes["periodo"] == resumo["ultimo_periodo"][frequencia])]
    area = ultimo["incidencia_periodo"].abs().where(ultimo["nivel"] == 3, 0)
    figura = go.Figure(go.Treemap(ids=ultimo["componente"], labels=ultimo["componente"].map(nomes), parents=ultimo["pai"].fillna(""),
                                  values=area, branchvalues="remainder", customdata=ultimo["incidencia_periodo"],
                                  texttemplate="%{label}<br>%{customdata:+.2f} pp", meta={"componentes": list(ultimo["componente"])}))
    return figura


# ==== 4. Sazonalidade e difusão (a difusão aparece na aba Composição) ====
def tend_dessazonalizado(componentes, nomes, resumo):
    """Tirada a sazonalidade, a inflação de cada mês está acelerando ou perdendo força?"""
    linhas = [go.Scatter(x=serie(componentes, c).tail(36)["data"], y=serie(componentes, c).tail(36)["variacao_sa_mensal"], mode="lines",
                         name=nomes[c], meta={"componente": c, "marcadores": "todos"}) for c in ("indice_general", "subyacente")]
    return go.Figure(linhas).update_layout(yaxis_title="variação mensal dessazonalizada (%)")


def tend_momentum(componentes, nomes, resumo):
    """O ritmo recente do núcleo está acima ou abaixo da inflação em 12 meses?"""
    # se o SAAR está abaixo da anual, a anual tende a cair nos próximos meses, e vice-versa. O 6 meses vem primeiro
    # e em destaque porque é o mais estável dos dois (docs/metodologia.md)
    nucleo = serie(componentes, "subyacente")
    tracos = [go.Scatter(x=nucleo["data"], y=nucleo[coluna], mode="lines", name=nome, meta={"componente": "subyacente", "medida": coluna})
              for coluna, nome in (("saar_6m", "SAAR 6 meses"), ("saar_3m", "SAAR 3 meses"), ("variacao_anual", "Variação em 12 meses"))]
    return com_meta(go.Figure(tracos).update_layout(yaxis_title="% ao ano"))


def perfil_sazonal(componentes, componente):
    """A variação mensal do ano corrente e dos 3 anteriores de um componente contra o seu padrão sazonal de 2010-2019."""
    # a faixa vai do p25 ao p75 da variação mensal de 2010-2019, e a outra linha é a mediana; tudo já vem das métricas.
    # Os anos saem do ano do último dado, e a cor e o traço vão pela distância a ele (ano_0 é o corrente), igual em todo perfil
    mensal = componentes[(componentes["componente"] == componente) & (componentes["frequencia"] == "mensal")]
    norma = mensal.assign(mes=mensal["data"].dt.month).drop_duplicates("mes").sort_values("mes")  # a norma se repete todo ano, basta uma linha por mês
    meses = norma["rotulo_mes"].str[:3].tolist()  # "ago/26" vira "ago", porque aqui o eixo é o mês do ano e não uma data
    tracos = [go.Scatter(x=meses, y=norma["norma_p25"], mode="lines", name="Faixa p25–p75", meta={"serie": "norma_p25"}),
              go.Scatter(x=meses, y=norma["norma_p75"], mode="lines", fill="tonexty", name="Faixa p25–p75", meta={"serie": "norma_p75"}),
              go.Scatter(x=meses, y=norma["norma_mediana"], mode="lines", name="Mediana 2010–2019", meta={"serie": "norma_mediana", "marcadores": "nenhum"})]
    corrente = mensal["data"].max().year
    for distancia in (3, 2, 1, 0):   # o ano corrente por último, para ficar por cima
        ano = mensal[mensal["data"].dt.year == corrente - distancia].sort_values("data")
        tracos.append(go.Scatter(x=meses[:len(ano)], y=ano["variacao_periodo"], mode="lines", name=str(corrente - distancia),
                                 meta={"serie": f"ano_{distancia}", "marcadores": "todos" if distancia == 0 else "nenhum"}))
    return go.Figure(tracos).update_layout(yaxis_title="variação mensal (%)")


def tend_perfil_sazonal(componentes, nomes, resumo):
    """Este ano o INPC está subindo mais ou menos do que é normal em cada mês?"""
    return perfil_sazonal(componentes, "indice_general")


# o nível logo abaixo do INPC e do núcleo, e os dois grupos do não núcleo, onde a sazonalidade é mais forte
# (o subsídio de verão da eletricidade em abr-mai e a volta em out-nov, por exemplo)
def sazon_perfil_subyacente(componentes, nomes, resumo):
    """O núcleo está subindo mais ou menos do que é normal em cada mês?"""
    return perfil_sazonal(componentes, "subyacente")


def sazon_perfil_no_subyacente(componentes, nomes, resumo):
    """O não núcleo está subindo mais ou menos do que é normal em cada mês?"""
    return perfil_sazonal(componentes, "no_subyacente")


def sazon_perfil_mercancias(componentes, nomes, resumo):
    """Mercadorias estão subindo mais ou menos do que é normal em cada mês?"""
    return perfil_sazonal(componentes, "mercancias")


def sazon_perfil_servicios(componentes, nomes, resumo):
    """Serviços estão subindo mais ou menos do que é normal em cada mês?"""
    return perfil_sazonal(componentes, "servicios")


def sazon_perfil_agropecuarios(componentes, nomes, resumo):
    """Agropecuários estão subindo mais ou menos do que é normal em cada mês?"""
    return perfil_sazonal(componentes, "agropecuarios")


def sazon_perfil_energeticos(componentes, nomes, resumo):
    """Energia e tarifas estão subindo mais ou menos do que é normal em cada mês?"""
    return perfil_sazonal(componentes, "energeticos_y_tarifas")


def tend_difusao(difusao, resumo):
    """A inflação está espalhada pela cesta ou concentrada em poucos itens?"""
    # cada linha leva junto a cobertura (parte do peso da cesta com dado e número de itens), que o tooltip mostra
    tracos = [go.Scatter(x=difusao["data"], y=difusao[coluna], mode="lines", name=nome, meta={"serie": coluna, "cobertura": True},
                         customdata=difusao[[f"cobertura_peso_{base}", f"itens_validos_{base}"]].values)
              for coluna, nome, base in (("pct_cesta_em_alta", "% do peso com alta no mês", "mes"),
                                         ("pct_cesta_anual_acima_3", "% do peso com alta acima de 3% em 12 meses", "anual"))]
    return go.Figure(tracos).update_layout(yaxis_title="% do peso da cesta")


# ==== 5. Composição: grupos no formato do Informe Trimestral do Banxico ====
# cada categoria vira um par: à esquerda a variação em 12 meses do pai e dos filhos, à direita quanto cada filho
# contribuiu para a variação em 12 meses do pai. As duas funções genéricas servem a qualquer pai e filhos
def valores(componentes, componente, coluna, inicio, mes_base):
    """A série mensal a partir de inicio e a última quinzena de um componente; com mês-base, as duas viram a mudança desde ele."""
    mensal, quinzena = serie(componentes, componente), serie(componentes, componente, "quinzenal").tail(1)
    mensal = mensal[mensal["periodo"] >= inicio]
    if mes_base is None:
        return mensal, quinzena
    base = mensal.loc[mensal["periodo"] == mes_base, coluna].iloc[0]
    return mensal.assign(**{coluna: mensal[coluna] - base}), quinzena.assign(**{coluna: quinzena[coluna] - base})


def traco(tabela, coluna, componente, nome, papel, tipo, quinzena=False):
    """Uma linha ou barra; o papel (pai ou filho) e a marca de quinzena vão em meta para o template escolher o visual."""
    # a última quinzena entra como um ponto depois do último mês, como o Banxico faz ("F1-August")
    meta = {"componente": componente, "papel": papel, "quinzena": quinzena}
    if quinzena:
        nome = f"{nome} · {tabela['rotulo_periodo'].iloc[0]} (quinzenal)"
        meta["rotulo_quinzena"] = tabela["rotulo_periodo"].iloc[0]
    classe, modo = (go.Bar, {}) if tipo == "barra" else (go.Scatter, {"mode": "markers" if quinzena else "lines"})
    return classe(x=tabela["data"], y=tabela[coluna], name=nome, showlegend=not quinzena, meta=meta, **modo)


def tracos_da_serie(componentes, nomes, resumo, componente, coluna, papel, tipo, inicio="", mes_base=None):
    """O traço mensal de um componente e, se o último release foi de quinzena, o ponto dela na ponta."""
    mensal, quinzena = valores(componentes, componente, coluna, inicio, mes_base)
    tracos = [traco(mensal, coluna, componente, nomes[componente], papel, tipo)]
    if resumo["frequencia_do_release"] == "quinzenal":
        tracos.append(traco(quinzena, coluna, componente, nomes[componente], papel, tipo, quinzena=True))
    return tracos


def par_anual(componentes, nomes, resumo, pai, filhos):
    """Variação em 12 meses do pai (a linha escura) e de cada filho."""
    tracos = [t for c in [pai, *filhos] for t in tracos_da_serie(componentes, nomes, resumo, c, "variacao_anual", "pai" if c == pai else "filho", "linha")]
    return go.Figure(tracos).update_layout(yaxis_title="variação em 12 meses (%)")


def par_contribuicoes(componentes, nomes, resumo, pai, filhos, coluna="contribuicao_no_pai", mes_base=None):
    """Barras empilhadas com a contribuição de cada filho para a variação em 12 meses do pai, e o pai como linha."""
    # as barras somam a linha: a contribuição já vem na base do pai (metricas.py). O gráfico começa no mês-base ou
    # no primeiro mês com contribuição: o INEGI não publica a incidência de ago/2018, quando a base mudou,
    # e a soma de 12 meses precisa de todas, então antes de ago/2019 não há barra para bater com a linha
    inicio = mes_base or serie(componentes, filhos[0]).dropna(subset=[coluna])["periodo"].iloc[0]
    # tudo sai em %, no formato do Banxico: a barra é quanto cada filho soma à variação em 12 meses do pai, que é a linha
    barras = [t for c in filhos for t in tracos_da_serie(componentes, nomes, resumo, c, coluna, "filho", "barra", inicio, mes_base)]
    linha_do_pai = tracos_da_serie(componentes, nomes, resumo, pai, "variacao_anual", "pai", "linha", inicio, mes_base)
    return go.Figure(barras + linha_do_pai).update_layout(barmode="relative", yaxis_title="contribuição (%)")


def grupos_inpc_anual(componentes, nomes, resumo):
    """O INPC e seus dois grupos, núcleo e não núcleo, contra a meta."""
    return com_meta(par_anual(componentes, nomes, resumo, "indice_general", ["subyacente", "no_subyacente"]))


def grupos_inpc_contrib(componentes, nomes, resumo):
    """Quanto o núcleo e o não núcleo somam à inflação em 12 meses."""
    return par_contribuicoes(componentes, nomes, resumo, "indice_general", ["subyacente", "no_subyacente"])


def grupos_nucleo_anual(componentes, nomes, resumo):
    """O núcleo e seus dois grupos, mercadorias e serviços."""
    return par_anual(componentes, nomes, resumo, "subyacente", ["mercancias", "servicios"])


def grupos_nucleo_contrib(componentes, nomes, resumo):
    """Quanto mercadorias e serviços somam à variação em 12 meses do núcleo."""
    return par_contribuicoes(componentes, nomes, resumo, "subyacente", ["mercancias", "servicios"])


def grupos_mercadorias_anual(componentes, nomes, resumo):
    """Mercadorias: alimentos, bebidas e tabaco, e mercadorias não alimentícias."""
    return par_anual(componentes, nomes, resumo, "mercancias", ["alimentos_bebidas_y_tabaco", "mercancias_no_alimenticias"])


def grupos_mercadorias_contrib(componentes, nomes, resumo):
    """Quanto cada grupo de mercadorias soma à variação em 12 meses de mercadorias."""
    return par_contribuicoes(componentes, nomes, resumo, "mercancias", ["alimentos_bebidas_y_tabaco", "mercancias_no_alimenticias"])


def grupos_servicos_anual(componentes, nomes, resumo):
    """Serviços: habitação, educação e outros serviços."""
    return par_anual(componentes, nomes, resumo, "servicios", ["vivienda", "educacion_colegiaturas", "otros_servicios"])


def grupos_servicos_contrib(componentes, nomes, resumo):
    """Quanto habitação, educação e outros serviços somam à variação em 12 meses de serviços."""
    return par_contribuicoes(componentes, nomes, resumo, "servicios", ["vivienda", "educacion_colegiaturas", "otros_servicios"])


def grupos_nao_nucleo_anual(componentes, nomes, resumo):
    """O não núcleo e seus dois grupos, agropecuários e energia e tarifas."""
    return par_anual(componentes, nomes, resumo, "no_subyacente", ["agropecuarios", "energeticos_y_tarifas"])


def grupos_nao_nucleo_desde_base(componentes, nomes, resumo):
    """O que explicou a mudança do não núcleo desde o mês-base: a contribuição de cada subíndice menos a do mês-base."""
    # a contribuição aqui é para o não núcleo (contribuicao_no_grupo), não para agropecuários ou energia e tarifas
    subindices = ["frutas_y_verduras", "pecuarios", "energeticos", "tarifas_autorizadas_por_el_gobierno"]
    figura = par_contribuicoes(componentes, nomes, resumo, "no_subyacente", subindices, "contribuicao_no_grupo", p.MES_BASE_NAO_NUCLEO)
    base = serie(componentes, "no_subyacente").set_index("periodo").loc[p.MES_BASE_NAO_NUCLEO]
    # o subtítulo vai junto da figura porque depende do mês-base, que é parâmetro
    subtitulo = f"Mudança desde {base['rotulo_periodo']} na contribuição de cada subíndice para a variação em 12 meses do não núcleo (%)"
    return figura.update_layout(meta={"subtitulo": subtitulo})


# ==== 6. Explorar: o mesmo par para todas as categorias ====
def peso_no_inpc(ponderadores, componente):
    """Peso do componente na cesta 2024, em % do INPC: a soma dos genéricos que estão dentro dele."""
    if componente == "indice_general":
        return 100.0
    pesos = ponderadores[ponderadores["cesta"] == "2024"]
    dentro = pesos[["subindice", "componente_nivel2", "componente_nivel1"]].eq(componente).any(axis=1)
    return pesos.loc[dentro, "ponderador"].sum()


def explorar(componentes, aberturas, ponderadores, nomes, resumo):
    """Um par de gráficos por categoria, na ordem da árvore: os grupos de cada componente e as aberturas de cada subíndice."""
    # a hierarquia vem da coluna pai do catálogo, que já está na ordem da árvore (cada pai seguido dos seus descendentes).
    # Quem tem filhos no catálogo mostra os filhos; os subíndices, que não têm, mostram as aberturas de maior peso
    catalogo = pd.read_csv(p.CATALOGO, dtype=str)
    catalogo = catalogo[(catalogo["tipo"] == "indice") & (catalogo["frequencia"] == "mensal")]
    figuras = {}
    for componente in catalogo["componente"]:
        nome = nomes[componente]
        filhos = catalogo.loc[catalogo["pai"] == componente, "componente"].tolist()
        if filhos:
            tabela, nomes_do_bloco, barras = componentes, nomes, filhos
            subtitulos = (f"{nome} e seus grupos: variação em 12 meses, %",
                          f"Contribuição para a variação em 12 meses de {nome} (%): a soma das barras é a linha")
        else:
            do_subindice = aberturas[aberturas["pai"] == componente]
            tabela = pd.concat([componentes[componentes["componente"] == componente], do_subindice])
            nomes_do_bloco = {componente: nome, **dict(zip(do_subindice["componente"], do_subindice["nome"]))}
            barras = sorted(do_subindice["componente"].unique())  # abertura_1, abertura_2... e, se houver, demais
            primeiro = do_subindice[do_subindice["frequencia"] == "mensal"].dropna(subset=["contribuicao_no_pai"]).sort_values("data")["rotulo_periodo"].iloc[0]
            quantas = len(barras) - ("demais" in barras)
            subtitulos = (f"{nome} e as {quantas} aberturas de maior peso na cesta 2024: variação em 12 meses, %",
                          f"Contribuição para a variação em 12 meses de {nome} (%): a soma das barras é a linha. As barras são as "
                          f"{quantas} aberturas de maior peso{' e as demais' if 'demais' in barras else ''} e começam em {primeiro}, "
                          f"o primeiro mês com 12 meses inteiros na cesta 2024")
        linhas = [b for b in barras if b != "demais"]  # "Demais" é resto, não tem variação própria
        anual = par_anual(tabela, nomes_do_bloco, resumo, componente, linhas)
        figuras[f"explorar_{componente}_anual"] = (com_meta(anual) if componente == "indice_general" else anual).update_layout(
            meta={"bloco": nome, "peso": round(peso_no_inpc(ponderadores, componente), 2), "subtitulo": subtitulos[0]})
        figuras[f"explorar_{componente}_contrib"] = par_contribuicoes(tabela, nomes_do_bloco, resumo, componente, barras).update_layout(
            meta={"subtitulo": subtitulos[1]})
    return figuras


if __name__ == "__main__":
    inicio = time.time()
    componentes, difusao = ler("metricas_componentes"), ler("metricas_difusao")
    nomes = p.NOMES_EXIBICAO
    resumo = json.loads((p.PASTA_PROCESSED / "metricas_resumo.json").read_text(encoding="utf-8"))
    slots = [main_inpc_meta, main_core_meta, main_vs_norma, decomp_arvore,
             tend_dessazonalizado, tend_momentum, tend_perfil_sazonal,
             sazon_perfil_subyacente, sazon_perfil_no_subyacente, sazon_perfil_mercancias, sazon_perfil_servicios,
             sazon_perfil_agropecuarios, sazon_perfil_energeticos,
             grupos_inpc_anual, grupos_inpc_contrib, grupos_nucleo_anual, grupos_nucleo_contrib, grupos_mercadorias_anual,
             grupos_mercadorias_contrib, grupos_servicos_anual, grupos_servicos_contrib, grupos_nao_nucleo_anual, grupos_nao_nucleo_desde_base]
    figuras = {slot.__name__: slot(componentes, nomes, resumo) for slot in slots}
    figuras["tend_difusao"] = tend_difusao(difusao[difusao["data"].dt.year >= p.ANO_INICIO_GRAFICOS], resumo)
    figuras.update(explorar(componentes, ler("metricas_aberturas"), ler("ponderadores"), nomes, resumo))
    saida = {}
    for slot, figura in figuras.items():
        figura.update_layout(separators=",.")  # vírgula decimal, como no resto do dashboard
        saida[slot] = json.loads(figura.to_json())
        saida[slot]["layout"].pop("template", None)
    (p.PASTA_PROCESSED / "graficos.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    print(f"Gráficos: {len(saida)} figuras; {time.time() - inicio:.1f} s")
