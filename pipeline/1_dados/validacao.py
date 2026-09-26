# Etapa 1.3: Validação
# Antes de fazer qualquer conta, confiro se a base está inteira e se reproduz o que o INEGI publicou.
# São quatro checagens: (1) nas janelas que o dashboard usa, os 16 componentes têm índice e incidência
# em todos os períodos, sem buraco, inclusive nos lags da variação anual; (2) o tabulado oficial é do
# mesmo período que a base, porque um tabulado velho confere com o mês velho e não prova nada;
# (3) a base reproduz o tabulado do último release; (4) as incidências somam a variação do INPC.
# Um nulo nunca passa: qualquer valor comparado que falte vira falha, com o que faltou na mensagem.
# Se uma falhar, paro o pipeline antes das métricas: prefiro o dashboard de ontem a um com número errado.

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p


# ==== 1. Tabelas de apoio ====
def periodo_da_posicao(posicao, frequencia):
    """O rótulo "2026-08" ou "2026-09-Q1" de uma posição, para a mensagem dizer qual período falta."""
    mes = posicao // 2 if frequencia == "quinzenal" else posicao
    rotulo = f"{mes // 12}-{mes % 12 + 1:02d}"
    return f"{rotulo}-Q{posicao % 2 + 1}" if frequencia == "quinzenal" else rotulo


def janela(series, tipo, frequencia, periodos, componentes):
    """Os últimos períodos da base como tabela posição x componente, na grade completa: período ou componente que falta vira nulo."""
    # a grade vem da posição e da lista do catálogo, não do que está na base; assim o que sumiu aparece como buraco
    selecao = series[(series["tipo"] == tipo) & (series["frequencia"] == frequencia)]
    fim = series[series["frequencia"] == frequencia]["posicao"].max()
    tabela = selecao.pivot(index="posicao", columns="componente", values="valor")
    return tabela.reindex(index=range(fim - periodos + 1, fim + 1), columns=componentes)


def desvio_maximo(desvios, nome):
    """O maior desvio, mas só se nenhum for nulo; o max() do Python pulava o NaN em silêncio."""
    desvios = pd.Series(desvios, dtype=float)
    if desvios.isna().any():
        raise SystemExit(f"Validação falhou: {nome} tem {int(desvios.isna().sum())} valor(es) nulo(s) na comparação. Pipeline interrompido.")
    return float(desvios.max())


# ==== 2. Checagens ====
def conferir_completude(series, componentes):
    """Nas janelas conferidas, cada um dos 16 componentes tem índice e incidência em todos os períodos."""
    # a janela é a da aditividade mais um ano, porque a variação anual do primeiro período precisa do índice de 12 meses antes
    faltas = []
    for frequencia, periodos in p.PERIODOS_POR_ANO.items():
        tamanho = p.MESES_VALIDACAO_ADITIVIDADE * periodos // 12 + periodos
        for tipo in ("indice", "incidencia"):
            nulos = janela(series, tipo, frequencia, tamanho, componentes).isna().stack()
            faltas += [f"{tipo} de {componente} em {periodo_da_posicao(posicao, frequencia)}" for (posicao, componente), nulo in nulos.items() if nulo]
    return faltas


def conferir_tabulado_em_dia(series, oficial):
    """O tabulado oficial tem de ser do último período da base, senão a comparação seguinte confere o mês errado."""
    atrasos = []
    for frequencia in p.PERIODOS_POR_ANO:
        ultimo_na_base = series[series["frequencia"] == frequencia].sort_values("posicao")["periodo"].iloc[-1]
        no_tabulado = set(oficial[oficial["frequencia"] == frequencia]["periodo"])
        if no_tabulado != {ultimo_na_base}:
            atrasos.append(f"{frequencia}: tabulado {sorted(no_tabulado)} e base {ultimo_na_base}")
    return atrasos


def conferir_ultimo_release(series, oficial, componentes):
    """Recalculo variação, anual e incidência dos 16 componentes no último release e comparo com o tabulado do INEGI."""
    # faço a conta aqui de propósito, sem usar a etapa de métricas: a validação tem de ser independente dela.
    # Os lags saem da grade de posições, então um período intermediário ausente vira nulo e não um lag errado
    desvios = []
    for frequencia, periodos in p.PERIODOS_POR_ANO.items():
        indices = janela(series, "indice", frequencia, periodos + 1, componentes)
        fim = indices.index.max()
        calculado = {"variacao": (indices.loc[fim] / indices.loc[fim - 1] - 1) * 100,
                     "variacao_anual": (indices.loc[fim] / indices.loc[fim - periodos] - 1) * 100,
                     "incidencia": janela(series, "incidencia", frequencia, 1, componentes).loc[fim]}
        publicado = oficial[oficial["frequencia"] == frequencia].set_index("componente").reindex(componentes)  # componente fora do tabulado vira nulo
        for medida, valores in calculado.items():
            desvios += list((valores - publicado[medida]).abs())
    return desvio_maximo(desvios, "último release vs tabulado oficial")


def conferir_aditividade(series, componentes):
    """Nos últimos 24 meses, a incidência do núcleo mais a do não núcleo tem de dar a variação do INPC geral."""
    # incidência é quanto cada parte puxou a inflação, em pontos percentuais; as partes somam o todo.
    # Sem dropna: um período sem dado na janela é falha, não um período a menos na conta
    desvios = []
    for frequencia, periodos in p.PERIODOS_POR_ANO.items():
        tamanho = p.MESES_VALIDACAO_ADITIVIDADE * periodos // 12  # a janela é em meses; no quinzenal isso dá o dobro de períodos
        geral = janela(series, "indice", frequencia, tamanho + 1, componentes)["indice_general"]
        variacao = ((geral / geral.shift(1) - 1) * 100).iloc[1:]
        incidencias = janela(series, "incidencia", frequencia, tamanho, componentes)
        desvios += list((incidencias["subyacente"] + incidencias["no_subyacente"] - variacao).abs())
    return desvio_maximo(desvios, "incidências somam o INPC")


if __name__ == "__main__":
    series = pd.read_parquet(p.PASTA_PROCESSED / "series.parquet")
    oficial = pd.read_parquet(p.PASTA_PROCESSED / "tabulado_oficial.parquet")
    componentes = pd.read_csv(p.CATALOGO, encoding="utf-8")["componente"].unique().tolist()  # os 16 que o catálogo diz que existem
    # as duas primeiras dizem se dá para comparar; se falharem, as comparações nem rodam
    for nome, problemas in (("base completa nas janelas conferidas", conferir_completude(series, componentes)),
                            ("tabulado oficial do mesmo período da base", conferir_tabulado_em_dia(series, oficial))):
        print(f"Validação: {nome}: {'ok' if not problemas else 'FALHOU'}")
        if problemas:
            raise SystemExit(f"Validação falhou: {nome}. Faltando ou fora do lugar: {'; '.join(problemas[:5])}"
                             f"{f' (e mais {len(problemas) - 5})' if len(problemas) > 5 else ''}. Pipeline interrompido.")
    checagens = {"ultimo release vs tabulado oficial": conferir_ultimo_release(series, oficial, componentes),
                 f"incidencias somam o INPC geral ({p.MESES_VALIDACAO_ADITIVIDADE} meses)": conferir_aditividade(series, componentes)}
    resultado = {nome: {"desvio_maximo_pp": round(desvio, 6), "ok": desvio <= p.TOLERANCIA_VALIDACAO_PP} for nome, desvio in checagens.items()}
    for nome, item in resultado.items():
        print(f"Validação: {nome}: {'ok' if item['ok'] else 'FALHOU'} (desvio máximo {item['desvio_maximo_pp']} pp, tolerância {p.TOLERANCIA_VALIDACAO_PP})")
    ultimo = series.sort_values("posicao").groupby("frequencia")["periodo"].last().to_dict()
    relatorio = {"data": datetime.now(ZoneInfo(p.FUSO)).isoformat(timespec="seconds"), "ultimo_periodo": ultimo, "checagens": resultado}
    (p.PASTA_PROCESSED / "validacao.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    falhas = [nome for nome, item in resultado.items() if not item["ok"]]
    if falhas:
        raise SystemExit(f"Validação falhou: {'; '.join(falhas)}. Pipeline interrompido.")
