# Etapa 1.3: Validação
# Antes de fazer qualquer conta, confiro se a base reproduz o que o INEGI publicou. São só duas
# checagens, escolhidas porque juntas pegam quase tudo: a primeira recalcula o último release e
# compara com o tabulado oficial (se um dado faltar ou vier trocado, aparece aqui); a segunda vê se
# as incidências somam a inflação do INPC, o que só acontece se índices e incidências forem coerentes.
# Se uma falhar, paro o pipeline antes da montagem: prefiro o dashboard de ontem a um com número
# errado. O resultado fica em validacao.json, para eu consultar depois.

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p


# ==== 1. Tabelas de apoio ====
def tabela(series, tipo, frequencia):
    """Uma frequência de índices ou de incidências como tabela período x componente, em ordem de data."""
    selecao = series[(series["tipo"] == tipo) & (series["frequencia"] == frequencia)]
    return selecao.pivot(index="periodo", columns="componente", values="valor").sort_index()


# ==== 2. Checagens ====
def conferir_ultimo_release(series, oficial):
    """Recalculo variação, anual e incidência dos 16 componentes no último release e comparo com o tabulado do INEGI."""
    # faço a conta aqui de propósito, sem usar a etapa de métricas: a validação tem de ser independente dela
    desvios = []
    for frequencia, periodos in p.PERIODOS_POR_ANO.items():
        indices = tabela(series, "indice", frequencia)
        calculado = {"variacao": (indices / indices.shift(1) - 1) * 100,
                     "variacao_anual": (indices / indices.shift(periodos) - 1) * 100,
                     "incidencia": tabela(series, "incidencia", frequencia)}
        for _, linha in oficial[oficial["frequencia"] == frequencia].iterrows():
            desvios += [abs(calculado[medida].at[linha["periodo"], linha["componente"]] - linha[medida]) for medida in calculado]
    return max(desvios)


def conferir_aditividade(series):
    """Nos últimos 24 meses, a incidência da subyacente mais a da no subyacente tem de dar a variação do INPC geral."""
    # incidência é quanto cada parte puxou a inflação, em pontos percentuais; as partes somam o todo
    desvios = []
    for frequencia, periodos in p.PERIODOS_POR_ANO.items():
        geral = tabela(series, "indice", frequencia)["indice_general"]
        variacao = (geral / geral.shift(1) - 1) * 100
        incidencias = tabela(series, "incidencia", frequencia)
        soma = incidencias["subyacente"] + incidencias["no_subyacente"]
        # a janela é em meses; no quinzenal isso dá o dobro de períodos
        desvios.append((soma - variacao).dropna().tail(p.MESES_VALIDACAO_ADITIVIDADE * periodos // 12).abs().max())
    return max(desvios)


if __name__ == "__main__":
    series = pd.read_parquet(p.PASTA_PROCESSED / "series.parquet")
    oficial = pd.read_parquet(p.PASTA_PROCESSED / "tabulado_oficial.parquet")
    checagens = {"ultimo release vs tabulado oficial": conferir_ultimo_release(series, oficial),
                 f"incidencias somam o INPC geral ({p.MESES_VALIDACAO_ADITIVIDADE} meses)": conferir_aditividade(series)}
    resultado = {nome: {"desvio_maximo_pp": round(float(desvio), 6), "ok": bool(desvio <= p.TOLERANCIA_VALIDACAO_PP)} for nome, desvio in checagens.items()}
    for nome, item in resultado.items():
        print(f"Validação: {nome}: {'ok' if item['ok'] else 'FALHOU'} (desvio máximo {item['desvio_maximo_pp']} pp, tolerância {p.TOLERANCIA_VALIDACAO_PP})")
    ultimo = series.sort_values("data").groupby("frequencia")["periodo"].last().to_dict()
    relatorio = {"data": datetime.now(ZoneInfo(p.FUSO)).isoformat(timespec="seconds"), "ultimo_periodo": ultimo, "checagens": resultado}
    (p.PASTA_PROCESSED / "validacao.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    falhas = [nome for nome, item in resultado.items() if not item["ok"]]
    if falhas:
        raise SystemExit(f"Validação falhou: {'; '.join(falhas)}. Pipeline interrompido.")
