# Etapa 1.4: Dessazonalização
# Tiro o padrão sazonal do índice mensal dos 16 componentes, para ler a variação de um mês como
# tendência e não como calendário (as colegiaturas sobem todo agosto, a eletricidade cai todo abril
# com o subsídio de verão). Uso o STL do statsmodels, robusto a outliers, no log do índice e só de
# 2000 para cá, porque antes a inflação alta afoga a sazonalidade. Escolhi STL e não X-13 porque o
# STL é Python puro e dá o mesmo resultado em qualquer máquina, sem instalar o programa do Census;
# o X-13 é o que as agências usam e seria o próximo passo.
# O quinzenal eu não dessazonalizo. O STL aceitaria um ciclo de 24 quinzenas; quem não aceita é o X-13,
# que só trabalha com dado mensal ou trimestral. Escolhi não fazer porque o mensal já é a média das duas
# quinzenas e é nele que o ritmo é lido; para a quinzena a leitura sazonal é a mediana histórica das métricas.

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p


# ==== 1. Ajuste sazonal ====
def dessazonalizar(indice):
    """O índice sem a parte sazonal que o STL enxerga, num ciclo de 12 meses."""
    # no log a sazonalidade vira proporcional: agosto sobe x% a mais todo ano, e não x pontos, o que faz sentido com o índice crescendo
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
