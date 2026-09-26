# Etapa 3.1: Montagem do dashboard
# Junta tudo num único HTML que abre sem internet (vai por e-mail): o template com o visual,
# o plotly.js embutido e os dados do release (gráficos, tabelas, cabeçalho e frases de destaque).
# O cabeçalho responde o que o economista quer saber às 06:00: qual release saiu, quando sai o
# próximo, se a base passou na validação e os números principais. As frases de destaque são
# geradas por regra, só com fatos do metricas_resumo.json, sem opinião.
# Lê: pipeline/3_dashboard/template.html, data/processed (graficos, tabelas, metricas_resumo)
# e config/calendario_releases.csv. Escreve: output/dashboard_inpc.html.

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from plotly.offline import get_plotlyjs

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para a etapa rodar sozinha: a raiz do projeto entra no caminho do Python
from config import parametros as p



# ==== 1. Formatação ====
def numero(valor, casas=2, sufixo="%", sinal=False):
    """Número em português: vírgula decimal, sinal de menos tipográfico e sufixo."""
    if round(valor, casas) == 0:
        valor = 0.0  # o que arredonda para zero sai "0,00", sem "+" nem "−"
    texto = f"{valor:+.{casas}f}" if sinal and valor else f"{valor:.{casas}f}"
    return texto.replace("-", "−").replace(".", ",") + sufixo


# ==== 2. Cabeçalho ====
def releases():
    """Calendário oficial com o momento de cada divulgação no horário da Cidade do México."""
    calendario = pd.read_csv(p.CALENDARIO, dtype=str, encoding="utf-8")
    calendario["momento"] = pd.to_datetime(calendario["data_divulgacao"] + " " + calendario["hora_local"]).dt.tz_localize(p.FUSO)
    return calendario


def kpi(principal, frequencia):
    """Cartão de um componente: variação no período, anual e quanto a anual mudou contra o período anterior."""
    mudanca = round(principal["mudanca_da_anual_pp"], 2)  # o que se vê na tela decide a seta: -0,001 é "0,00", neutro
    return {"variacao_periodo": numero(principal["variacao_periodo"]), "variacao_anual": numero(principal["variacao_anual"]),
            "rotulo_periodo": "na quinzena" if frequencia == "quinzenal" else "no mês",
            "mudanca": numero(mudanca, sufixo=" pp", sinal=True), "seta": "▲" if mudanca > 0 else "▼" if mudanca < 0 else "=",
            "classe": "alta" if mudanca > 0 else "baixa" if mudanca < 0 else "neutro", "anterior": principal["rotulo_anterior"]}


def mensal_implicito(implicito):
    """Cartão do mês corrente estimado no dia da 1a quinzena, com o intervalo p25 a p75."""
    geral, nucleo = implicito["indice_general"], implicito["subyacente"]
    return {"mes": implicito["rotulo_mes"],
            "variacao_mensal": numero(geral["mediana"]["variacao_mensal"]), "variacao_anual": numero(geral["mediana"]["variacao_anual"]),
            "intervalo_mensal": f"{numero(geral['p25']['variacao_mensal'])} a {numero(geral['p75']['variacao_mensal'])}",
            "intervalo_anual": f"{numero(geral['p25']['variacao_anual'])} a {numero(geral['p75']['variacao_anual'])}",
            "subyacente": f"{numero(nucleo['mediana']['variacao_mensal'])} no mês · {numero(nucleo['mediana']['variacao_anual'])} em 12 meses"}


def proximo_release(calendario, agora):
    """Data do próximo release e dias até lá; depois do último release do ano o calendário precisa ser estendido."""
    futuros = calendario[calendario["momento"] > agora]
    if futuros.empty:
        return {"proximo": f"calendário {int(calendario['data_divulgacao'].max()[:4]) + 1} ainda não carregado", "dias_ate_proximo": None}
    momento = futuros["momento"].iloc[0]
    return {"proximo": f"{momento:%d/%m/%Y %H:%M}", "dias_ate_proximo": (momento.date() - agora.date()).days}


def cabecalho(resumo, agora):
    """Tudo o que a barra superior e os cartões de KPI mostram."""
    # o dashboard só é montado depois que a validação passou, então o que ele mostra já foi conferido
    frequencia = resumo["frequencia_do_release"]
    periodo = resumo["ultimo_periodo"][frequencia]
    calendario = releases()
    divulgado = calendario[(calendario["tipo"] == resumo["tipo_ultimo_release"]) & (calendario["periodo_referencia"] == periodo[:7])]
    return {"release": resumo["ultimo_rotulo"][frequencia], "ano": periodo[:4], "divulgado": f"{divulgado['momento'].iloc[0]:%d/%m %H:%M}",
            **proximo_release(calendario, agora), "atualizado": f"{agora:%d/%m %H:%M}", "conferido": resumo["ultimo_rotulo"][frequencia],
            "frequencia": frequencia,
            "kpis": [{"nome": p.NOMES_EXIBICAO[componente], **kpi(principal, frequencia)}
                     for componente, principal in resumo["principais"][frequencia].items()],
            "mensal_implicito": mensal_implicito(resumo["mensal_implicito"]) if resumo["mensal_implicito"] else None}


# ==== 3. Destaques do release ====
def nome(item):
    """Nome do genérico com a primeira letra maiúscula."""
    return item["nome_generico"][:1].upper() + item["nome_generico"][1:]


def destaques(resumo):
    """3 a 4 frases com os fatos do release, geradas por regra a partir do resumo (sem opinião)."""
    frequencia = resumo["frequencia_do_release"]
    geral, nucleo = resumo["principais"][frequencia]["indice_general"], resumo["principais"][frequencia]["subyacente"]
    maior = resumo["destaques"]["maiores_incidencias"][0]
    acima, abaixo = resumo["destaques"]["acima_da_norma"][0], resumo["destaques"]["abaixo_da_norma"][0]
    difusao = resumo["difusao"]
    anual = (f"INPC {numero(geral['variacao_anual'])} a/a ({numero(geral['mudanca_da_anual_pp'], sufixo=' pp', sinal=True)}); "
             f"subyacente {numero(nucleo['variacao_anual'])} ({numero(nucleo['mudanca_da_anual_pp'], sufixo=' pp', sinal=True)})")
    incidencia = f"Maior incidência: {nome(maior)} {numero(maior['incidencia_periodo'], 3, ' pp', True)} ({numero(maior['variacao_periodo'], sinal=True)})"
    surpresa = (f"Maior surpresa vs norma: {nome(acima)} {numero(acima['contribuicao_surpresa'], 3, ' pp', True)}; "
                f"para baixo: {nome(abaixo)} {numero(abaixo['contribuicao_surpresa'], 3, ' pp', True)}")
    espalhamento = f"{numero(difusao['pct_cesta_anual_acima_3'], 0)} da cesta com inflação anual acima de 3% ({difusao['rotulo_periodo']})"
    return [anual, incidencia, surpresa, espalhamento]


def ler(nome_arquivo):
    """JSON de data/processed."""
    return json.loads((p.PASTA_PROCESSED / nome_arquivo).read_text(encoding="utf-8"))


if __name__ == "__main__":
    agora = datetime.now(ZoneInfo(p.FUSO))
    resumo = ler("metricas_resumo.json")
    dados = {"graficos": ler("graficos.json"), "tabelas": ler("tabelas.json"),
             "cabecalho": cabecalho(resumo, agora), "destaques": destaques(resumo)}
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    # "</" dentro de um <script> fecharia a tag antes da hora; escapar a barra não muda o JSON
    dados_js = "window.DADOS = " + json.dumps(dados, ensure_ascii=False).replace("</", "<\\/") + ";"
    html = template.replace("/*__PLOTLY__*/", get_plotlyjs()).replace("/*__DADOS__*/", dados_js)
    destino = p.PASTA_OUTPUT / "dashboard_inpc.html"
    destino.write_text(html, encoding="utf-8")
    print(f"Montagem: {destino.name} com {destino.stat().st_size / 1e6:.1f} MB")
