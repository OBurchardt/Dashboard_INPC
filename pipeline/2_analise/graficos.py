# Etapa 2.3: Gráficos
# Monta as figuras do dashboard com plotly, só com conteúdo: dados, tipo de traço, nomes das séries,
# títulos dos eixos e as marcas de referência (meta de 3% do Banxico e intervalo de 2% a 4%).
# Nenhum estilo aqui (cores, fontes, template): tudo isso é do template HTML, que reconhece cada
# componente pelo campo "meta" do traço e aplica a cor fixa dele. Nada é calculado neste arquivo:
# os números vêm prontos de metricas.py.
# Lê: data/processed (metricas_componentes, metricas_difusao, metricas_resumo); nomes curtos de config/parametros.py.
# Escreve: data/processed/graficos.json = {slot: figura}.

import json
import sys
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para a etapa rodar sozinha: a raiz do projeto entra no caminho do Python
from config import parametros as p

pio.templates.default = "none"  # sem o template padrão do plotly, que traria cores e fontes


# ==== 1. Apoio ====
def ler(nome):
    """Tabela de data/processed."""
    return pd.read_parquet(p.PASTA_PROCESSED / f"{nome}.parquet")


def serie(componentes, componente, frequencia="mensal"):
    """Linhas de um componente numa frequência desde o início do histórico dos gráficos, em ordem cronológica."""
    tabela = componentes[(componentes["componente"] == componente) & (componentes["frequencia"] == frequencia)]
    return tabela[tabela["data"].dt.year >= p.ANO_INICIO_GRAFICOS].sort_values("data")


def linha(tabela, coluna, componente, nome):
    """Traço de linha de um componente, marcado com o componente para o template aplicar a cor."""
    return go.Scatter(x=tabela["data"], y=tabela[coluna], mode="lines", name=nome, meta={"componente": componente})


def com_meta(figura):
    """Acrescenta a meta de inflação do Banxico (3%) e o intervalo de tolerância (2% a 4%)."""
    figura.add_hrect(y0=2, y1=4, name="banda_meta")
    figura.add_hline(y=3, name="meta")
    return figura


# ==== 2. Visão principal ====
def anual_com_meta(componentes, componente, nome):
    """Variação anual mensal de um componente contra a meta, com a última quinzena destacada."""
    quinzena = serie(componentes, componente, "quinzenal").iloc[-1]
    figura = go.Figure([linha(serie(componentes, componente), "variacao_anual", componente, nome),
                        go.Scatter(x=[quinzena["data"]], y=[quinzena["variacao_anual"]], mode="markers",
                                   name=f"Última quinzena ({quinzena['rotulo_periodo']})", showlegend=False,
                                   meta={"componente": componente, "destaque": "ultima_quinzena"})])
    figura.update_layout(yaxis_title="variação em 12 meses (%)")
    return com_meta(figura)


def main_inpc_meta(componentes, nomes, resumo):
    """A inflação cheia está dentro da meta do Banxico? E a última quinzena aponta para onde?"""
    return anual_com_meta(componentes, "indice_general", nomes["indice_general"])


def main_core_meta(componentes, nomes, resumo):
    """O núcleo, que é o que o Banxico olha para a política monetária, está convergindo para 3%?"""
    return anual_com_meta(componentes, "subyacente", nomes["subyacente"])


def main_contribuicoes(componentes, nomes, resumo):
    """De onde vem a inflação anual: mercadorias, serviços, agropecuários ou energéticos?"""
    # os últimos 24 meses mostram se a composição da inflação está mudando
    barras = [go.Bar(x=serie(componentes, c).tail(24)["data"], y=serie(componentes, c).tail(24)["contribuicao_anual"],
                     name=nomes[c], meta={"componente": c}) for c in p.COMPONENTES_NIVEL_2]
    geral = serie(componentes, "indice_general").tail(24)
    figura = go.Figure(barras + [linha(geral, "variacao_anual", "indice_general", nomes["indice_general"])])
    return figura.update_layout(barmode="relative", yaxis_title="contribuição à inflação em 12 meses (pp)")


def main_vs_norma(componentes, nomes, resumo):
    """O último dado veio acima ou abaixo do que costuma acontecer nesse período do ano?"""
    # barras horizontais para os nomes caberem sem rotação; a norma é a mediana de 2010-2019 do mesmo
    # mês ou quinzena, e a barra de erro vai do p25 ao p75
    frequencia = resumo["frequencia_do_release"]
    ultimo = componentes[(componentes["frequencia"] == frequencia) & (componentes["periodo"] == resumo["ultimo_periodo"][frequencia])]
    ultimo = ultimo.set_index("componente").loc[[*p.COMPONENTES_PRINCIPAIS, *p.COMPONENTES_NIVEL_2]]
    rotulos = [nomes[c] for c in ultimo.index]
    barras = [go.Bar(y=[nomes[c]], x=[ultimo.at[c, "variacao_periodo"]], orientation="h", name=nomes[c], meta={"componente": c})
              for c in ultimo.index]
    norma = go.Scatter(y=rotulos, x=ultimo["norma_mediana"], mode="markers", name="Norma 2010-2019 (mediana)", meta={"serie": "norma"},
                       error_x={"type": "data", "symmetric": False, "array": ultimo["norma_p75"] - ultimo["norma_mediana"],
                                "arrayminus": ultimo["norma_mediana"] - ultimo["norma_p25"]})
    figura = go.Figure(barras + [norma])
    # a ordem de cima para baixo é a da lista: INPC, subyacente, no subyacente e o nível 2
    return figura.update_layout(barmode="overlay", yaxis={"autorange": "reversed"},
                                xaxis_title=f"variação em {resumo['ultimo_rotulo'][frequencia]} (%)")


# ==== 3. Decomposição ====
def decomp_arvore(componentes, nomes, resumo):
    """Quanto cada parte do INPC contribuiu para a variação do último período, do todo até os subíndices?"""
    # a área é o tamanho da contribuição (em módulo) dos subíndices; o número mostrado mantém o sinal
    frequencia = resumo["frequencia_do_release"]
    ultimo = componentes[(componentes["frequencia"] == frequencia) & (componentes["periodo"] == resumo["ultimo_periodo"][frequencia])]
    area = ultimo["incidencia_periodo"].abs().where(ultimo["nivel"] == 3, 0)
    figura = go.Figure(go.Treemap(ids=ultimo["componente"], labels=ultimo["componente"].map(nomes), parents=ultimo["pai"].fillna(""),
                                  values=area, branchvalues="remainder", customdata=ultimo["incidencia_periodo"],
                                  texttemplate="%{label}<br>%{customdata:+.3f} pp", meta={"componentes": list(ultimo["componente"])}))
    return figura


def decomp_servicos_mercancias(componentes, nomes, resumo):
    """A inflação de serviços, mais inercial, está descolando da de mercadorias?"""
    figura = go.Figure([linha(serie(componentes, c), "variacao_anual", c, nomes[c]) for c in ("servicios", "mercancias")])
    return figura.update_layout(yaxis_title="variação em 12 meses (%)")


# ==== 4. Tendência ====
def tend_dessazonalizado(componentes, nomes, resumo):
    """Tirando a sazonalidade, a inflação de cada mês está acelerando ou desacelerando?"""
    barras = [go.Bar(x=serie(componentes, c).tail(36)["data"], y=serie(componentes, c).tail(36)["variacao_sa_mensal"],
                     name=nomes[c], meta={"componente": c}) for c in ("indice_general", "subyacente")]
    return go.Figure(barras).update_layout(barmode="group", yaxis_title="variação mensal dessazonalizada (%)")


def tend_momentum(componentes, nomes, resumo):
    """O ritmo recente do núcleo (3 e 6 meses anualizados) está abaixo ou acima da variação em 12 meses?"""
    # se o SAAR de 3 meses está abaixo da anual, a inflação anual tende a cair nos próximos meses
    nucleo = serie(componentes, "subyacente")
    tracos = [go.Scatter(x=nucleo["data"], y=nucleo[coluna], mode="lines", name=nome, meta={"componente": "subyacente", "medida": coluna})
              for coluna, nome in (("saar_3m", "SAAR 3 meses"), ("saar_6m", "SAAR 6 meses"), ("variacao_anual", "Variação em 12 meses"))]
    return com_meta(go.Figure(tracos).update_layout(yaxis_title="% ao ano"))


def tend_perfil_sazonal(componentes, nomes, resumo):
    """Este ano está subindo mais ou menos do que é normal em cada mês?"""
    # a faixa é o intervalo p25-p75 da variação mensal de 2010-2019 e a linha do meio, a mediana
    geral = componentes[(componentes["componente"] == "indice_general") & (componentes["frequencia"] == "mensal")]
    norma = geral.assign(mes=geral["data"].dt.month).drop_duplicates("mes").sort_values("mes")  # a norma se repete todo ano
    ano = geral[geral["data"].dt.year == geral["data"].max().year]
    meses = norma["rotulo_mes"].str[:3].tolist()  # "ago/26" vira "ago": no perfil o eixo é o mês do ano
    tracos = [go.Scatter(x=meses, y=norma["norma_p25"], mode="lines", name="Norma p25", meta={"serie": "norma_p25"}),
              go.Scatter(x=meses, y=norma["norma_p75"], mode="lines", fill="tonexty", name="Norma p75", meta={"serie": "norma_p75"}),
              go.Scatter(x=meses, y=norma["norma_mediana"], mode="lines", name="Norma (mediana)", meta={"serie": "norma_mediana"}),
              go.Scatter(x=meses[:len(ano)], y=ano["variacao_periodo"], mode="lines+markers", name=str(ano["data"].max().year),
                         meta={"componente": "indice_general"})]
    return go.Figure(tracos).update_layout(yaxis_title="variação mensal do INPC (%)")


def tend_difusao(difusao, resumo):
    """A inflação está espalhada pela cesta ou concentrada em poucos itens?"""
    tracos = [go.Scatter(x=difusao["data"], y=difusao[coluna], mode="lines", name=nome, meta={"serie": coluna})
              for coluna, nome in (("pct_cesta_em_alta", "% da cesta com alta no mês"),
                                   ("pct_cesta_anual_acima_4", "% da cesta com alta acima de 4% em 12 meses"))]
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
