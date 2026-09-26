# Etapa 1.4 — Dessazonalização
# Tira o padrão sazonal do índice mensal dos 16 componentes (ex.: a alta das colegiaturas em
# agosto ou o fim do subsídio de eletricidade no outono), para que a variação de um mês possa ser
# lida como tendência. Método: STL do statsmodels, robusto a outliers, aplicado ao log do índice
# de 2000 em diante. Escolhemos STL e não o X-13 porque o STL é Python puro e roda igual em
# qualquer máquina e no GitHub Actions, sem instalar o binário do Census Bureau; o X-13 é o
# padrão das agências oficiais e seria a evolução natural do projeto.
# O quinzenal não é dessazonalizado: os métodos padrão não trabalham com 24 períodos por ano.
# Para ele, a leitura sazonal é a comparação com a norma histórica, feita em metricas.py.

import time

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from config import parametros as p


# ==== 1. Ajuste sazonal ====
def dessazonalizar(indice):
    """Índice sem o componente sazonal estimado pelo STL (período de 12 meses, robusto)."""
    # no log, a sazonalidade é multiplicativa: o mesmo mês pesa x% a mais todo ano, não x pontos
    ajuste = STL(np.log(indice), period=12, robust=True).fit()
    return np.exp(np.log(indice) - ajuste.seasonal)


if __name__ == "__main__":
    inicio = time.time()
    series = pd.read_parquet(p.PASTA_PROCESSED / "series.parquet")
    mensal = series[(series["tipo"] == "indice") & (series["frequencia"] == "mensal")
                    & (series["data"].dt.year >= p.ANO_INICIO_DESSAZONALIZACAO)]
    ajustadas = []
    for componente, serie in mensal.groupby("componente"):
        serie = serie.sort_values("data")
        indice_sa = dessazonalizar(serie.set_index("data")["valor"])
        ajustadas.append(pd.DataFrame({"componente": componente, "periodo": serie["periodo"].values,
                                       "data": serie["data"].values, "indice_sa": indice_sa.values}))
    resultado = pd.concat(ajustadas)
    resultado.to_parquet(p.PASTA_PROCESSED / "series_dessazonalizadas.parquet", index=False)
    print(f"Dessazonalização: {resultado['componente'].nunique()} componentes, {len(resultado)} linhas; {time.time() - inicio:.1f} s")
