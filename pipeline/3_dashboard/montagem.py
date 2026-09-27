# Etapa 3.1: Montagem do dashboard
# Junto tudo num único HTML que abre sem internet, porque ele vai por e-mail: o template com o
# visual, o plotly.js embutido e os dados do release. O que é só desta etapa é o cabeçalho (qual
# release saiu e quando, quando sai o próximo, os números dos cartões já formatados) e as quatro
# frases de destaque, só com fatos do resumo, sem opinião. "Desvio sazonal" é contra a mediana de
# 2010 a 2019, não contra expectativa de mercado, por isso não chamo de surpresa. Esta etapa só
# roda se a validação passou, então tudo o que ela mostra já foi conferido com o INEGI.

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from plotly.offline import get_plotlyjs

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p


# ==== 1. Leitura e formatação ====
def ler(nome_arquivo):
    """Um JSON de data/processed."""
    return json.loads((p.PASTA_PROCESSED / nome_arquivo).read_text(encoding="utf-8"))


def numero(valor, casas=2, sufixo="%", sinal=False):
    """Número como a gente escreve: vírgula decimal, o sinal de menos de verdade e o sufixo."""
    if round(valor, casas) == 0:
        valor = 0.0  # o que arredonda para zero sai "0,00", sem "+" nem "−"
    texto = f"{valor:+.{casas}f}" if sinal and valor else f"{valor:.{casas}f}"
    return texto.replace("-", "−").replace(".", ",") + sufixo


# ==== 2. Cabeçalho ====
def releases():
    """O calendário oficial, com o horário de cada divulgação no fuso da Cidade do México."""
    calendario = pd.read_csv(p.CALENDARIO, dtype=str, encoding="utf-8")
    calendario["momento"] = pd.to_datetime(calendario["data_divulgacao"] + " " + calendario["hora_local"]).dt.tz_localize(p.FUSO)
    return calendario


def kpi(principal, frequencia):
    """Um cartão: variação no período, em 12 meses, e se a de 12 meses subiu ou caiu desde o período anterior."""
    mudanca = round(principal["mudanca_da_anual_pp"], 2)  # decido a seta pelo que aparece na tela: −0,001 vira "0,00" e fica neutro
    return {"variacao_periodo": numero(principal["variacao_periodo"]), "variacao_anual": numero(principal["variacao_anual"]),
            "rotulo_periodo": "na quinzena" if frequencia == "quinzenal" else "no mês",
            "mudanca": numero(mudanca, sufixo=" pp", sinal=True), "seta": "▲" if mudanca > 0 else "▼" if mudanca < 0 else "=",
            "classe": "alta" if mudanca > 0 else "baixa" if mudanca < 0 else "neutro", "anterior": principal["rotulo_anterior"]}


def mensal_implicito(implicito):
    """O cartão do mês estimado no dia da 1a quinzena, com a faixa dos erros do backtest e quantas vezes ela acertou."""
    geral, nucleo = implicito["indice_general"], implicito["subyacente"]
    return {"mes": implicito["rotulo_mes"],
            "variacao_mensal": numero(geral["mediana"]["variacao_mensal"]), "variacao_anual": numero(geral["mediana"]["variacao_anual"]),
            "intervalo_mensal": f"{numero(geral['p25']['variacao_mensal'])} a {numero(geral['p75']['variacao_mensal'])}",
            "intervalo_anual": f"{numero(geral['p25']['variacao_anual'])} a {numero(geral['p75']['variacao_anual'])}",
            "cobertura": numero(geral["cobertura_da_faixa"], 0), "meses_testados": geral["meses_testados"],
            "subyacente": f"{numero(nucleo['mediana']['variacao_mensal'])} no mês · {numero(nucleo['mediana']['variacao_anual'])} em 12 meses"}


def proximo_release(calendario, agora):
    """Quando sai o próximo e em quantos dias; depois do último release do arquivo, digo que falta o calendário novo."""
    futuros = calendario[calendario["momento"] > agora]
    if futuros.empty:
        return {"proximo": f"calendário {int(calendario['data_divulgacao'].max()[:4]) + 1} ainda não carregado", "dias_ate_proximo": None}
    momento = futuros["momento"].iloc[0]
    return {"proximo": f"{momento:%d/%m/%Y %H:%M}", "dias_ate_proximo": (momento.date() - agora.date()).days}


def cabecalho(resumo, agora):
    """Tudo o que a faixa do topo e os cartões mostram, já em texto."""
    frequencia = resumo["frequencia_do_release"]
    periodo = resumo["ultimo_periodo"][frequencia]
    calendario = releases()
    divulgado = calendario[(calendario["tipo"] == resumo["tipo_ultimo_release"]) & (calendario["periodo_referencia"] == periodo[:7])]
    return {"release": resumo["ultimo_rotulo"][frequencia], "ano": periodo[:4], "divulgado": f"{divulgado['momento'].iloc[0]:%d/%m %H:%M}",
            **proximo_release(calendario, agora), "atualizado": f"{agora:%d/%m %H:%M}", "conferido": resumo["ultimo_rotulo"][frequencia],
            "frequencia": frequencia,
            "kpis": [{"componente": componente, "nome": p.NOMES_EXIBICAO[componente], **kpi(principal, frequencia)}
                     for componente, principal in resumo["principais"][frequencia].items()],
            "mensal_implicito": mensal_implicito(resumo["mensal_implicito"]) if resumo["mensal_implicito"] else None}


# ==== 3. Destaques do release ====
def nome(item):
    """O nome do genérico com a primeira letra maiúscula, que é como ele aparece numa frase."""
    return item["nome_generico"][:1].upper() + item["nome_generico"][1:]


def destaques(resumo):
    """As quatro frases do topo: ritmo do núcleo, maior contribuição, maior desvio sazonal e difusão, só com os fatos."""
    ritmo = resumo["ritmo_do_nucleo"]
    maior = resumo["destaques"]["maiores_incidencias"][0]
    acima, abaixo = resumo["destaques"]["acima_da_norma"][0], resumo["destaques"]["abaixo_da_norma"][0]
    difusao = resumo["difusao"]
    # a inflação do release já está na faixa e nos cartões; aqui vai o ritmo do núcleo contra a anual do mesmo mês
    nucleo = f"SAAR 6 meses {numero(ritmo['saar_6m'])} ({ritmo['rotulo_periodo']}) vs {numero(ritmo['variacao_anual'])} em 12 meses"
    contribuicao = f"Maior contribuição: {nome(maior)} {numero(maior['incidencia_periodo'], sufixo=' pp', sinal=True)} ({numero(maior['variacao_periodo'], sinal=True)})"
    desvio = (f"Maior desvio sazonal ponderado: {nome(acima)} {numero(acima['desvio_sazonal_ponderado'], sufixo=' pp', sinal=True)}; "
              f"para baixo: {nome(abaixo)} {numero(abaixo['desvio_sazonal_ponderado'], sufixo=' pp', sinal=True)}")
    # sem ": " no texto, porque o template usa o primeiro ": " da frase para separar o rótulo
    espalhamento = f"{numero(difusao['pct_cesta_anual_acima_3'], 0)} do peso da cesta com alta acima de 3% em 12 meses ({difusao['rotulo_periodo']})"
    return [nucleo, contribuicao, desvio, espalhamento]


if __name__ == "__main__":
    agora = datetime.now(ZoneInfo(p.FUSO))
    resumo = ler("metricas_resumo.json")
    dados = {"graficos": ler("graficos.json"), "tabelas": ler("tabelas.json"),
             "cabecalho": cabecalho(resumo, agora), "destaques": destaques(resumo)}
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    # cuidado: um "</" dentro do <script> fecharia a tag antes da hora; escapar a barra não muda o JSON
    dados_js = "window.DADOS = " + json.dumps(dados, ensure_ascii=False).replace("</", "<\\/") + ";"
    html = template.replace("/*__PLOTLY__*/", get_plotlyjs()).replace("/*__DADOS__*/", dados_js)
    destino = p.PASTA_OUTPUT / "dashboard_inpc.html"
    destino.write_text(html, encoding="utf-8")
    # o mesmo HTML como index.html, que é a página que a Vercel serve a partir de output/
    (p.PASTA_OUTPUT / "index.html").write_text(html, encoding="utf-8")
    print(f"Montagem: {destino.name} e index.html com {destino.stat().st_size / 1e6:.1f} MB")
