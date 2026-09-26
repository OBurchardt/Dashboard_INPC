# Etapa 2.3: Gráficos
# Aqui eu monto as dez figuras do dashboard com plotly, mas só o conteúdo: os dados, o tipo de
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
def anual_com_meta(componentes, componente, nome):
    """A inflação em 12 meses de um componente contra a meta, com a última quinzena como um ponto à parte."""
    # a linha é mensal e o ponto é quinzenal: no dia da 1a quinzena ele é o dado mais novo que existe
    quinzena = serie(componentes, componente, "quinzenal").iloc[-1]
    figura = go.Figure([linha(serie(componentes, componente), "variacao_anual", componente, nome),
                        go.Scatter(x=[quinzena["data"]], y=[quinzena["variacao_anual"]], mode="markers",
                                   name=f"Última quinzena ({quinzena['rotulo_periodo']})", showlegend=False,
                                   meta={"componente": componente, "destaque": "ultima_quinzena"})])
    figura.update_layout(yaxis_title="variação em 12 meses (%)")
    return com_meta(figura)


def main_inpc_meta(componentes, nomes, resumo):
    """A inflação cheia está dentro da meta do Banxico, e para onde aponta a última quinzena?"""
    return anual_com_meta(componentes, "indice_general", nomes["indice_general"])


def main_core_meta(componentes, nomes, resumo):
    """O núcleo, que é o que o Banxico olha para decidir juros, está convergindo para 3%?"""
    return anual_com_meta(componentes, "subyacente", nomes["subyacente"])


def main_contribuicoes(componentes, nomes, resumo):
    """De onde vem a inflação em 12 meses: mercadorias, serviços, agropecuários ou energéticos?"""
    # dois anos bastam para ver se a composição está mudando
    barras = [go.Bar(x=serie(componentes, c).tail(24)["data"], y=serie(componentes, c).tail(24)["contribuicao_anual"],
                     name=nomes[c], meta={"componente": c}) for c in p.COMPONENTES_NIVEL_2]
    geral = serie(componentes, "indice_general").tail(24)
    figura = go.Figure(barras + [linha(geral, "variacao_anual", "indice_general", nomes["indice_general"])])
    return figura.update_layout(barmode="relative", yaxis_title="contribuição à inflação em 12 meses (pp)")


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


def decomp_servicos_mercancias(componentes, nomes, resumo):
    """Serviços, que são mais inerciais, estão se descolando de mercadorias?"""
    figura = go.Figure([linha(serie(componentes, c), "variacao_anual", c, nomes[c]) for c in ("servicios", "mercancias")])
    return figura.update_layout(yaxis_title="variação em 12 meses (%)")


# ==== 4. Tendência ====
def tend_dessazonalizado(componentes, nomes, resumo):
    """Tirada a sazonalidade, a inflação de cada mês está acelerando ou perdendo força?"""
    barras = [go.Bar(x=serie(componentes, c).tail(36)["data"], y=serie(componentes, c).tail(36)["variacao_sa_mensal"],
                     name=nomes[c], meta={"componente": c}) for c in ("indice_general", "subyacente")]
    return go.Figure(barras).update_layout(barmode="group", yaxis_title="variação mensal dessazonalizada (%)")


def tend_momentum(componentes, nomes, resumo):
    """O ritmo recente do núcleo está acima ou abaixo da inflação em 12 meses?"""
    # se o SAAR está abaixo da anual, a anual tende a cair nos próximos meses, e vice-versa. O 6 meses vem primeiro
    # e em destaque porque, no exercício pseudo-tempo-real (docs/auditoria_pre_chat.md), a ponta do 3 meses revisou mais
    nucleo = serie(componentes, "subyacente")
    tracos = [go.Scatter(x=nucleo["data"], y=nucleo[coluna], mode="lines", name=nome, meta={"componente": "subyacente", "medida": coluna})
              for coluna, nome in (("saar_6m", "SAAR 6 meses"), ("saar_3m", "SAAR 3 meses (revisa mais)"), ("variacao_anual", "Variação em 12 meses"))]
    return com_meta(go.Figure(tracos).update_layout(yaxis_title="% ao ano"))


def tend_perfil_sazonal(componentes, nomes, resumo):
    """Este ano está subindo mais ou menos do que é normal em cada mês?"""
    # a faixa vai do p25 ao p75 da variação mensal de 2010-2019, e a linha pontilhada é a mediana
    geral = componentes[(componentes["componente"] == "indice_general") & (componentes["frequencia"] == "mensal")]
    norma = geral.assign(mes=geral["data"].dt.month).drop_duplicates("mes").sort_values("mes")  # a norma se repete todo ano, basta uma linha por mês
    ano = geral[geral["data"].dt.year == geral["data"].max().year]
    meses = norma["rotulo_mes"].str[:3].tolist()  # "ago/26" vira "ago", porque aqui o eixo é o mês do ano e não uma data
    tracos = [go.Scatter(x=meses, y=norma["norma_p25"], mode="lines", name="Padrão sazonal p25", meta={"serie": "norma_p25"}),
              go.Scatter(x=meses, y=norma["norma_p75"], mode="lines", fill="tonexty", name="Padrão sazonal p75", meta={"serie": "norma_p75"}),
              go.Scatter(x=meses, y=norma["norma_mediana"], mode="lines", name="Padrão sazonal (mediana)", meta={"serie": "norma_mediana"}),
              go.Scatter(x=meses[:len(ano)], y=ano["variacao_periodo"], mode="lines+markers", name=str(ano["data"].max().year),
                         meta={"componente": "indice_general"})]
    return go.Figure(tracos).update_layout(yaxis_title="variação mensal do INPC (%)")


def tend_difusao(difusao, resumo):
    """A inflação está espalhada pela cesta ou concentrada em poucos itens?"""
    # cada linha leva junto a cobertura (parte do peso da cesta com dado e número de itens), que o tooltip mostra
    tracos = [go.Scatter(x=difusao["data"], y=difusao[coluna], mode="lines", name=nome, meta={"serie": coluna, "cobertura": True},
                         customdata=difusao[[f"cobertura_peso_{base}", f"itens_validos_{base}"]].values)
              for coluna, nome, base in (("pct_cesta_em_alta", "% do peso com alta no mês", "mes"),
                                         ("pct_cesta_anual_acima_4", "% do peso com alta acima de 4% em 12 meses", "anual"))]
    return go.Figure(tracos).update_layout(yaxis_title="% do peso da cesta")


if __name__ == "__main__":
    inicio = time.time()
    componentes, difusao = ler("metricas_componentes"), ler("metricas_difusao")
    nomes = p.NOMES_EXIBICAO
    resumo = json.loads((p.PASTA_PROCESSED / "metricas_resumo.json").read_text(encoding="utf-8"))
    slots = [main_inpc_meta, main_core_meta, main_contribuicoes, main_vs_norma, decomp_arvore, decomp_servicos_mercancias,
             tend_dessazonalizado, tend_momentum, tend_perfil_sazonal]
    figuras = {slot.__name__: slot(componentes, nomes, resumo) for slot in slots}
    figuras["tend_difusao"] = tend_difusao(difusao[difusao["data"].dt.year >= p.ANO_INICIO_GRAFICOS], resumo)
    saida = {}
    for slot, figura in figuras.items():
        figura.update_layout(separators=",.")  # vírgula decimal, como no resto do dashboard
        saida[slot] = json.loads(figura.to_json())
        saida[slot]["layout"].pop("template", None)
    (p.PASTA_PROCESSED / "graficos.json").write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    print(f"Gráficos: {len(saida)} figuras; {time.time() - inicio:.1f} s")
