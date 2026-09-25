# Etapa 1.3 — Validação
# Antes de qualquer análise, confere se a base tratada reproduz os números oficiais do INEGI.
# São duas checagens. A primeira compara o último release com o tabulado que o INEGI publica;
# a segunda confere se as incidências da base somam a inflação do INPC geral. Se uma falhar,
# o pipeline para, porque um dashboard com número errado é pior do que nenhum dashboard.
# O resultado vai para data/processed/validacao.json, para o dashboard exibir.

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from config import parametros as p

TOLERANCIA_PONTOS = 0.01  # o INEGI publica as variações com 2 casas decimais
PERIODOS_POR_ANO = {"mensal": 12, "quinzenal": 24}


# ==== 1. Tabelas de apoio ====
def tabela(series, tipo, frequencia):
    """Série de um tipo e frequência como tabela período x componente, em ordem cronológica."""
    selecao = series[(series["tipo"] == tipo) & (series["frequencia"] == frequencia)]
    return selecao.pivot(index="periodo", columns="componente", values="valor").sort_index()


# ==== 2. Checagens ====
def conferir_ultimo_release(series, oficial):
    """Nossa variação no período, variação anual e incidência dos 16 componentes vs o tabulado oficial do último release."""
    # se a base reproduz o que o INEGI publicou, ela está completa e correta no dado mais recente
    desvios = []
    for frequencia, periodos in PERIODOS_POR_ANO.items():
        indices = tabela(series, "indice", frequencia)
        calculado = {"variacao": (indices / indices.shift(1) - 1) * 100,
                     "variacao_anual": (indices / indices.shift(periodos) - 1) * 100,
                     "incidencia": tabela(series, "incidencia", frequencia)}
        for _, linha in oficial[oficial["frequencia"] == frequencia].iterrows():
            desvios += [abs(calculado[medida].at[linha["periodo"], linha["componente"]] - linha[medida]) for medida in calculado]
    return max(desvios)


def conferir_aditividade(series):
    """Nos últimos 24 meses, a incidência da subyacente + a da no subyacente = variação do INPC geral."""
    # a incidência mede quanto cada componente contribuiu para a inflação; as partes têm de somar o todo
    desvios = []
    for frequencia, periodos in PERIODOS_POR_ANO.items():
        geral = tabela(series, "indice", frequencia)["indice_general"]
        variacao = (geral / geral.shift(1) - 1) * 100
        incidencias = tabela(series, "incidencia", frequencia)
        soma = incidencias["subyacente"] + incidencias["no_subyacente"]
        desvios.append((soma - variacao).dropna().tail(2 * periodos).abs().max())
    return max(desvios)


if __name__ == "__main__":
    series = pd.read_parquet(p.PASTA_PROCESSED / "series.parquet")
    oficial = pd.read_parquet(p.PASTA_PROCESSED / "tabulado_oficial.parquet")
    checagens = {"ultimo release vs tabulado oficial": conferir_ultimo_release(series, oficial),
                 "incidencias somam o INPC geral (24 meses)": conferir_aditividade(series)}
    resultado = {nome: {"desvio_maximo_pp": round(float(desvio), 6), "ok": bool(desvio <= TOLERANCIA_PONTOS)} for nome, desvio in checagens.items()}
    for nome, item in resultado.items():
        print(f"Validação: {nome}: {'ok' if item['ok'] else 'FALHOU'} (desvio máximo {item['desvio_maximo_pp']} pp, tolerância {TOLERANCIA_PONTOS})")
    ultimo = series.sort_values("data").groupby("frequencia")["periodo"].last().to_dict()
    relatorio = {"data": datetime.now(ZoneInfo(p.FUSO)).isoformat(timespec="seconds"), "ultimo_periodo": ultimo, "checagens": resultado}
    (p.PASTA_PROCESSED / "validacao.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    falhas = [nome for nome, item in resultado.items() if not item["ok"]]
    if falhas:
        raise SystemExit(f"Validação falhou: {'; '.join(falhas)}. Pipeline interrompido.")
