# Etapa 3.1: Montagem do dashboard
# Junto tudo num único HTML que abre sem internet, porque ele vai por e-mail: o template com o
# visual, o plotly.js embutido e os dados do release. O que é só desta etapa é o cabeçalho (qual
# release saiu e quando, quando sai o próximo, os números dos cartões já formatados) e as quatro
# frases de destaque, só com fatos do resumo, sem opinião. "Desvio sazonal" é contra a mediana de
# 2010 a 2019, não contra expectativa de mercado, por isso não chamo de surpresa. Esta etapa só
# roda se a validação passou, então tudo o que ela mostra já foi conferido com o INEGI.
# Ela também leva ao HTML o snapshot e o registro das visualizações do assistente, e grava em web/
# a cópia do HTML e o pacote de dados que a versão online usa.

import html
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
    """Um cartão: variação em 12 meses, no período, e quanto a de 12 meses mudou contra um mês antes."""
    # a mudança é entre as duas taxas como elas aparecem na tela (3,79% − 3,93% = −0,14 pp), que é a conta que o
    # mercado faz com os números publicados; a diferença sem arredondar podia dar −0,15 e parecer erro
    agora, antes = round(principal["variacao_anual"], 2), round(principal["variacao_anual_um_mes_antes"], 2)
    mudanca = round(agora - antes, 2)
    return {"variacao_periodo": numero(principal["variacao_periodo"]), "variacao_anual": numero(agora),
            "rotulo_periodo": "na quinzena" if frequencia == "quinzenal" else "no mês",
            "mudanca": numero(mudanca, sufixo=" pp", sinal=True), "seta": "▲" if mudanca > 0 else "▼" if mudanca < 0 else "=",
            "classe": "alta" if mudanca > 0 else "baixa" if mudanca < 0 else "neutro",
            "anterior": principal["rotulo_um_mes_antes"], "anual_anterior": numero(antes)}


def mensal_implicito(implicito):
    """A estimativa do próximo número mensal, no dia da 1a quinzena, com a faixa dos erros do backtest e quantas vezes ela acertou."""
    geral, nucleo = implicito["indice_general"], implicito["subyacente"]
    return {"mes": implicito["rotulo_mes"],
            "variacao_mensal": numero(geral["mediana"]["variacao_mensal"]), "variacao_anual": numero(geral["mediana"]["variacao_anual"]),
            "intervalo_mensal": f"{numero(geral['p25']['variacao_mensal'])} a {numero(geral['p75']['variacao_mensal'])}",
            "intervalo_anual": f"{numero(geral['p25']['variacao_anual'])} a {numero(geral['p75']['variacao_anual'])}",
            "cobertura": numero(geral["cobertura_da_faixa"], 0), "meses_testados": geral["meses_testados"],
            "subyacente": f"{numero(nucleo['mediana']['variacao_mensal'])} no mês · {numero(nucleo['mediana']['variacao_anual'])} em 12 meses",
            "mercado": expectativa_do_mercado(implicito["expectativa"])}


def expectativa_do_mercado(esperadas):
    """A linha "Encuesta Citi espera 0,37% (núcleo 0,27%)" do bloco do próximo release, ou None sem expectativa."""
    geral, nucleo = esperadas.get("indice_general"), esperadas.get("subyacente")
    if not (geral or nucleo):
        return None
    fontes = list(dict.fromkeys(item["fonte"] for item in (geral, nucleo) if item))
    quem = fontes[0].split(",")[0].strip()  # o nome sem a data; a fonte inteira vai no tooltip
    if geral:
        texto = f"{quem} espera {numero(geral['esperado'])}" + (f" (núcleo {numero(nucleo['esperado'])})" if nucleo else "")
    else:
        texto = f"{quem} espera núcleo de {numero(nucleo['esperado'])}"
    # a fonte é texto livre do CSV manual e vai para dentro do HTML, então escapo
    return {"texto": html.escape(texto), "fonte": html.escape("; ".join(fontes))}


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
            # os cartões são o que o mercado cita no release: o INPC, o núcleo e, dentro dele, serviços e mercadorias.
            # O não núcleo fica só na faixa do release
            "kpis": [{"componente": componente, "nome": p.NOMES_EXIBICAO[componente], **kpi(resumo["principais"][frequencia][componente], frequencia)}
                     for componente in ("indice_general", "subyacente", "servicios", "mercancias")],
            "nao_nucleo": numero(resumo["principais"][frequencia]["no_subyacente"]["variacao_anual"]),
            "mensal_implicito": mensal_implicito(resumo["mensal_implicito"]) if resumo["mensal_implicito"] else None}


# ==== 3. Destaques do release ====
def nome(item):
    """O nome do genérico com a primeira letra maiúscula, que é como ele aparece numa frase."""
    return item["nome_generico"][:1].upper() + item["nome_generico"][1:]


def realizado_x_esperado(expectativa):
    """O primeiro destaque: INPC e núcleo no período contra o esperado, e de onde veio a expectativa."""
    # a diferença é entre os dois números já arredondados em 2 casas, como na pílula dos cartões
    linhas, fontes = [], []
    for indicador, nome_na_tela in (("indice_general", "INPC"), ("subyacente", "Núcleo")):
        item = expectativa["indicadores"].get(indicador)
        if item is None:
            linhas.append(f"{nome_na_tela}: sem expectativa cadastrada")
            continue
        realizado, esperado = round(item["realizado"], 2), round(item["esperado"], 2)
        diferenca = numero(round(realizado - esperado, 2), sufixo=chr(160) + "pp", sinal=True)
        linhas.append(f"{nome_na_tela} {numero(realizado)} vs {numero(esperado)} esperado ({diferenca})")
        fontes += [] if item["fonte"] in fontes else [item["fonte"]]
    if not fontes:
        return f"Sem expectativa cadastrada para {expectativa['rotulo_periodo']}"
    # a fonte é texto livre do CSV manual e vai para dentro do HTML, então escapo
    return "\n".join(linhas + [f"Fonte da expectativa: {html.escape('; '.join(fontes))}"])


def destaques(resumo):
    """As quatro frases do topo (realizado x expectativa, maiores contribuições, maior desvio sazonal e difusão), só com os fatos; o rótulo de cada uma fica no template."""
    maior = resumo["destaques"]["maiores_incidencias"][0]
    acima, abaixo = resumo["destaques"]["acima_da_norma"][0], resumo["destaques"]["abaixo_da_norma"][0]
    difusao = resumo["difusao"]
    # a que mais puxou e a que mais segurou, uma por linha
    menor = resumo["destaques"]["menores_incidencias"][0]
    contribuicao = "\n".join(f"{lado}: {nome(item)} {numero(item['incidencia_periodo'], sufixo=chr(160) + 'pp', sinal=True)} "
                             f"({numero(item['variacao_periodo'], sinal=True)})" for lado, item in (("Para cima", maior), ("Para baixo", menor)))
    # espaço não separável antes do "pp", para a unidade não quebrar de linha longe do número
    desvio = (f"Acima do padrão: {nome(acima)} {numero(acima['desvio_sazonal_ponderado'], sufixo=chr(160) + 'pp', sinal=True)} · "
              f"Abaixo: {nome(abaixo)} {numero(abaixo['desvio_sazonal_ponderado'], sufixo=chr(160) + 'pp', sinal=True)}")
    espalhamento = f"{numero(difusao['pct_cesta_anual_acima_3'], 0)} do peso da cesta com alta acima de 3% em 12 meses ({difusao['rotulo_periodo']})"
    return [realizado_x_esperado(resumo["expectativa"]), contribuicao, desvio, espalhamento]


# ==== 4. Assistente ====
def assistente(pacote):
    """O que o painel do chat precisa no navegador: o snapshot, o release, o endereço da versão online e o registro das visualizações."""
    # os números ficam no servidor; o navegador só precisa saber o que existe na tela para aplicar as ações do chat
    return {"snapshot_id": pacote["snapshot_id"], "release": pacote["release"]["rotulo"], "frequencia": pacote["release"]["frequencia_do_release"],
            "url_versao_online": p.URL_VERSAO_ONLINE, "visualizacoes": pacote["visualizacoes"]}


if __name__ == "__main__":
    agora = datetime.now(ZoneInfo(p.FUSO))
    resumo = ler("metricas_resumo.json")
    pacote = ler("pacote_assistente.json")
    dados = {"graficos": ler("graficos.json"), "tabelas": ler("tabelas.json"),
             "cabecalho": cabecalho(resumo, agora), "destaques": destaques(resumo), "assistente": assistente(pacote)}
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    # cuidado: um "</" dentro do <script> fecharia a tag antes da hora; escapar a barra não muda o JSON
    dados_js = "window.DADOS = " + json.dumps(dados, ensure_ascii=False).replace("</", "<\\/") + ";"
    html = template.replace("/*__PLOTLY__*/", get_plotlyjs()).replace("/*__DADOS__*/", dados_js)
    destino = p.PASTA_OUTPUT / "dashboard_inpc.html"
    destino.write_text(html, encoding="utf-8")
    # o mesmo HTML como index.html, que é a página que a Vercel serve a partir de output/
    (p.PASTA_OUTPUT / "index.html").write_text(html, encoding="utf-8")
    # a versão online com o chat é servida de web/: a mesma página e o pacote que o servidor consulta
    (p.PASTA_WEB / "public").mkdir(parents=True, exist_ok=True)
    (p.PASTA_WEB / "dados").mkdir(parents=True, exist_ok=True)
    (p.PASTA_WEB / "public" / "index.html").write_text(html, encoding="utf-8")
    (p.PASTA_WEB / "dados" / "pacote.json").write_text(json.dumps(pacote, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Montagem: {destino.name} e index.html com {destino.stat().st_size / 1e6:.1f} MB")
