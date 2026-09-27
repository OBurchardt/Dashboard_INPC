# Etapa 1.1: Ingestão
# Trago do INEGI tudo o que o dashboard usa e guardo em data/raw, em CSVs que abrem no
# Excel (uma linha por período, uma coluna por série). A fonte principal é o app "Índices de
# Precios", que é o único lugar com os subíndices e os 292 genéricos com histórico; junto vêm os
# xlsx de ponderadores e os tabulados do release, que uso como gabarito na validação.
# No dia a dia a etapa é preguiçosa de propósito: olha o calendário, e se não saiu dado novo nem
# vai à rede. Se saiu, rebaixa só os últimos meses e sobrescreve esses períodos. O histórico
# inteiro só é baixado quando eu peço (IMPORTAR_DO_ZERO) ou quando a base ficou muito para trás.
# No fim, a expectativa de inflação da pesquisa do Banxico, a única coisa que não vem do INEGI.

import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p

MESES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}


# ==== 1. Rede ====
def pedir(metodo, url, **argumentos):
    """GET ou POST com até 3 tentativas, porque o servidor do INEGI derruba conexão sem avisar."""
    cabecalhos = {"User-Agent": "Mozilla/5.0", **argumentos.pop("headers", {})}
    for tentativa in range(1, p.TENTATIVAS_REDE + 1):
        try:
            resposta = requests.request(metodo, url, timeout=p.TEMPO_LIMITE_SEGUNDOS, headers=cabecalhos, **argumentos)
            resposta.raise_for_status()
            return resposta
        except requests.RequestException:
            if tentativa == p.TENTATIVAS_REDE:
                raise
            time.sleep(5 * tentativa)


# ==== 2. Períodos ====
def periodo_padrao(rotulo):
    """O INEGI escreve 'Ago 2026' e '1Q Sep 2026'; eu guardo '2026-08' e '2026-09-Q1', que ordenam certo como texto."""
    partes = rotulo.split()
    quinzena = f"-Q{partes[0][0]}" if len(partes) == 3 else ""
    return f"{partes[-1]}-{MESES[partes[-2]]:02d}{quinzena}"


def mes_do_periodo(periodo):
    """Meses desde o ano zero, só para medir quantos meses a base está atrasada."""
    return int(periodo[:4]) * 12 + int(periodo[5:7]) - 1


# ==== 3. Árvore dos genéricos ====
def filhos_do_no(estrutura, id_no, nivel):
    """Pergunta ao app quem está pendurado num nó da árvore; a resposta vem em HTML, uma linha por filho."""
    carga = {"sigNivel": str(nivel), "idNodo": id_no, "esquemaBD": "", "paramfuente": "",
             "paramEstructura": estrutura, "notas": [], "open": False}
    html = pedir("POST", p.URL_ARVORE, json=carga).json()["d"]
    filhos = []
    for linha in re.findall(r"(?s)<tr .*?</tr>", html):
        serie = re.search(r"value='(\d+)'", linha)
        nome = re.search(r'data-title="([^"]*)"', linha).group(1)
        filhos.append({"id_no": re.search(r"data-id=(\d+)", linha).group(1), "nome": nome,
                       "id_serie": serie.group(1) if serie else None,
                       "generico": bool(serie) and bool(re.match(r"\d{3} ", nome)),  # genérico é quem tem código de 3 dígitos, tipo "001 Arroz"
                       "tem_filhos": "glyphicon-plus" in linha})
    return filhos


def varrer_arvore(estrutura, raiz):
    """Desce a árvore do objeto do gasto inteira, guardando de cada nó quem é o pai."""
    nos, pendentes = [], [(raiz, 1)]
    while pendentes:
        id_no, nivel = pendentes.pop()
        for filho in filhos_do_no(estrutura, id_no, nivel):
            if filho.pop("tem_filhos"):
                pendentes.append((filho["id_no"], nivel + 1))
            nos.append({**filho, "id_pai": id_no, "nivel": nivel})
    return nos


def baixar_arvore(frequencia):
    """Salva a árvore; se vier faltando genérico eu varro de novo, porque uma cesta incompleta passaria despercebida."""
    # às vezes o servidor devolve nó sem o id da série; a segunda varredura costuma vir inteira
    for _ in range(2):
        nos = varrer_arvore(*p.ARVORES[frequencia])
        genericos = sum(no["generico"] for no in nos)
        if genericos == 292:  # a cesta 2024 tem 292 genéricos, segundo o documento metodológico do INEGI
            break
    else:
        raise SystemExit(f"Árvore {frequencia} veio com {genericos} de 292 genéricos; tente de novo mais tarde.")
    (p.PASTA_RAW / f"arvore_genericos_{frequencia}.json").write_text(json.dumps(nos, ensure_ascii=False, indent=1), encoding="utf-8")


# ==== 4. Séries (exportador do app) ====
def ler_csv_exportador(texto):
    """O CSV do exportador tem um cabeçalho de texto solto; os dados começam na linha 'Fecha', que lista os ids."""
    linhas = list(csv.reader(io.StringIO(texto)))
    inicio = next(numero for numero, linha in enumerate(linhas) if linha and linha[0] == "Fecha")
    ids = [valor for valor in linhas[inicio][1:] if valor]
    dados = [linha for linha in linhas[inicio + 1:] if linha]
    return pd.DataFrame([linha[1:len(ids) + 1] for linha in dados], columns=ids,
                        index=pd.Index([periodo_padrao(linha[0]) for linha in dados], name="periodo"))


def exportar(estrutura, ids, ano_inicio, ano_fim):
    """Pede ao exportador as séries de uma estrutura entre dois anos, em lotes para não estourar o tempo."""
    lotes = []
    for inicio in range(0, len(ids), p.LOTE_EXPORTACAO_IDS):
        formulario = {"idEstructura": estrutura, "cuadro": estrutura, "cvEstructura": estrutura, "_formato": "CSV",
                      "_tipo": "Niveles", "_orient": "vertical", "_meta": "0", "_info": "", "esquema": "", "st": "",
                      "pf": "inp", "_anioI": ano_inicio, "_anioF": ano_fim,
                      "_series": "c|" + ",".join(ids[inicio:inicio + p.LOTE_EXPORTACAO_IDS]) + ","}
        # o exportador responde em Windows-1252, não em UTF-8; sem isso os acentos viram lixo
        lotes.append(ler_csv_exportador(pedir("POST", p.URL_EXPORTADOR, data=formulario).content.decode("cp1252")))
    return pd.concat(lotes, axis=1)


def conjuntos_de_series():
    """As seis tabelas que eu mantenho: componentes, incidências e genéricos, cada uma em mensal e quinzenal."""
    catalogo = pd.read_csv(p.CATALOGO, dtype=str, encoding="utf-8")
    conjuntos = []
    for (tipo, frequencia), estrutura in p.ESTRUTURAS.items():
        ids = catalogo[(catalogo["tipo"] == tipo) & (catalogo["frequencia"] == frequencia)]["id_serie"].tolist()
        nome = "componentes" if tipo == "indice" else "incidencias"
        conjuntos.append((f"{nome}_{frequencia}", estrutura, ids))
    # os ids dos genéricos não estão no catálogo; saem da árvore
    for frequencia, (estrutura, _) in p.ARVORES.items():
        arvore = json.loads((p.PASTA_RAW / f"arvore_genericos_{frequencia}.json").read_text(encoding="utf-8"))
        conjuntos.append((f"genericos_{frequencia}", estrutura, [no["id_serie"] for no in arvore if no["generico"]]))
    return conjuntos


def salvar_tabela(nome, tabela, sobrescrever_periodos=False):
    """Grava o CSV; na atualização, o que acabou de chegar substitui os mesmos períodos da base, e assim pego revisões."""
    caminho = p.PASTA_RAW / f"{nome}.csv"
    if sobrescrever_periodos:
        antiga = pd.read_csv(caminho, dtype=str, index_col="periodo", keep_default_na=False, encoding="utf-8")
        tabela = pd.concat([antiga.drop(tabela.index, errors="ignore"), tabela]).sort_index()
    tabela.to_csv(caminho, encoding="utf-8")


# ==== 5. Ponderadores e tabulados oficiais ====
def baixar_ponderadores():
    """Os dois xlsx oficiais: o peso de cada genérico e, marcado com X, o subíndice a que ele pertence."""
    for nome, url in p.URLS_PONDERADORES.items():
        (p.PASTA_RAW / nome).write_bytes(pedir("GET", url).content)


def baixar_tabulados():
    """O que o INEGI publicou no último release; guardo o período no meu formato para a validação saber o que comparar."""
    for frequencia, cuadro in p.TABULADOS.items():
        tabulado = pedir("GET", p.URL_TABULADO.format(cuadro=cuadro)).json()
        tabulado["periodo"] = periodo_padrao(tabulado["Encab"][0]["periodo_actual"])
        (p.PASTA_RAW / f"tabulado_{frequencia}.json").write_text(json.dumps(tabulado, ensure_ascii=False), encoding="utf-8")


# ==== 6. Calendário e base ====
def ultimo_divulgado():
    """O período mais recente que o INEGI já publicou em cada frequência, olhando só os releases que já aconteceram."""
    calendario = pd.read_csv(p.CALENDARIO, dtype=str, encoding="utf-8")
    momentos = pd.to_datetime(calendario["data_divulgacao"] + " " + calendario["hora_local"]).dt.tz_localize(p.FUSO)
    ocorridos = calendario[momentos <= datetime.now(ZoneInfo(p.FUSO))]
    mensais = ocorridos[ocorridos["tipo"] == "mensal_e_2a_quinzena"]["periodo_referencia"]
    primeiras = ocorridos[ocorridos["tipo"] == "1a_quinzena"]["periodo_referencia"]
    # cuidado: o release "mensal" traz também a 2a quinzena do mesmo mês; a 1a quinzena sai num release separado
    return {"mensal": mensais.max(), "quinzenal": max([f"{mes}-Q2" for mes in mensais] + [f"{mes}-Q1" for mes in primeiras])}


def ultimo_na_base():
    """O último período que todas as tabelas têm; fico com o menor, porque basta uma atrasada para a base estar atrasada."""
    ultimos = {}
    for frequencia in ("mensal", "quinzenal"):
        arquivos = [p.PASTA_RAW / f"{nome}_{frequencia}.csv" for nome in ("componentes", "incidencias", "genericos")]
        if not all(arquivo.exists() for arquivo in arquivos):
            return None
        ultimos[frequencia] = min(pd.read_csv(arquivo, usecols=["periodo"], encoding="utf-8")["periodo"].iloc[-1] for arquivo in arquivos)
    return ultimos


# ==== 7. Os dois modos ====
def baixar_historico_completo():
    """Tudo do zero: árvores, pesos, o histórico inteiro de cada série e os tabulados."""
    for frequencia in p.ARVORES:
        baixar_arvore(frequencia)
    baixar_ponderadores()
    for nome, estrutura, ids in conjuntos_de_series():
        salvar_tabela(nome, exportar(estrutura, ids, 1969, datetime.now(ZoneInfo(p.FUSO)).year))  # 1969 é o primeiro ano que o app oferece
    baixar_tabulados()
    print(f"Histórico completo baixado (último dado: {ultimo_na_base()})")


def avisar_se_o_calendario_acabou():
    """Se todos os releases do arquivo já passaram eu aviso, porque sem o calendário novo a base congela dizendo que está em dia."""
    calendario = pd.read_csv(p.CALENDARIO, dtype=str, encoding="utf-8")
    ultimo = pd.Timestamp(calendario["data_divulgacao"].max() + " " + calendario["hora_local"].iloc[-1]).tz_localize(p.FUSO)
    if datetime.now(ZoneInfo(p.FUSO)) > ultimo:
        print(f"Aviso: o calendário acaba em {ultimo:%d/%m/%Y}; acrescente o de {ultimo.year + 1} em config/calendario_releases.csv")


def atualizar():
    """O caminho de todo dia: compara a base com o calendário e só baixa o que falta."""
    avisar_se_o_calendario_acabou()
    divulgado, base = ultimo_divulgado(), ultimo_na_base()
    if base == divulgado:
        print(f"Já atualizado (último dado: {base['mensal']} e {base['quinzenal']})")
        return
    if base is None or max(mes_do_periodo(divulgado[f]) - mes_do_periodo(base[f]) for f in base) > p.MESES_JANELA_ATUALIZACAO:
        print("Base vazia ou muito atrasada: rodando histórico completo")
        baixar_historico_completo()
        return
    # o exportador só filtra por ano, então peço desde o ano do mês que fica 6 meses antes do último divulgado;
    # isso também fecha sozinho qualquer release que eu tenha deixado de rodar
    ano_inicio = (mes_do_periodo(divulgado["mensal"]) - p.MESES_JANELA_ATUALIZACAO) // 12
    for nome, estrutura, ids in conjuntos_de_series():
        salvar_tabela(nome, exportar(estrutura, ids, ano_inicio, datetime.now(ZoneInfo(p.FUSO)).year), sobrescrever_periodos=True)
    baixar_tabulados()
    print(f"Base atualizada de {base} para {ultimo_na_base()} (janela desde {ano_inicio})")


# ==== 8. Expectativas do Banxico ====
def token_do_banxico():
    """O token da API do Banxico: do ambiente (no GitHub, o secret) ou do .env local, que fica fora do git."""
    if not os.environ.get("BANXICO_TOKEN") and (p.RAIZ / ".env").exists():
        for linha in (p.RAIZ / ".env").read_text(encoding="utf-8").splitlines():
            chave, _, valor = linha.partition("=")
            if chave.strip() == "BANXICO_TOKEN":
                os.environ["BANXICO_TOKEN"] = valor.strip().strip('"')
    return os.environ.get("BANXICO_TOKEN")


def baixar_expectativas_banxico():
    """A mediana da inflação mensal esperada pela pesquisa do Banxico, INPC e núcleo, para data/raw/expectativas_banxico.csv."""
    # a única falha que eu deixo passar: sem token ou com a API fora, o dashboard sai sem a expectativa do Banxico,
    # porque a validação contra o INEGI não pode depender dele. A mensagem não traz a URL nem o token
    token = token_do_banxico()
    if not token:
        print("Expectativas do Banxico: sem BANXICO_TOKEN, sigo sem elas")
        return
    series = {serie: indicador for indicador, serie in p.SERIES_EXPECTATIVA_BANXICO.items()}
    try:
        resposta = pedir("GET", p.URL_BANXICO_SIE.format(series=",".join(series)), headers={"Bmx-Token": token}).json()
    except requests.RequestException as erro:
        print(f"Expectativas do Banxico: API indisponível ({type(erro).__name__}), sigo sem elas")
        return
    linhas = [{"periodo": f"{dado['fecha'][6:]}-{dado['fecha'][3:5]}", "indicador": series[serie["idSerie"]], "variacao_esperada": dado["dato"]}
              for serie in resposta["bmx"]["series"] for dado in serie["datos"] if dado["dato"] != "N/E"]  # fecha vem como "01/08/2026"
    tabela = pd.DataFrame(linhas).sort_values(["periodo", "indicador"])
    tabela.to_csv(p.PASTA_RAW / "expectativas_banxico.csv", index=False, encoding="utf-8")
    print(f"Expectativas do Banxico: pesquisas até {tabela['periodo'].max()}")


if __name__ == "__main__":
    inicio = time.time()
    if globals().get("importar_do_zero"):  # a opção chega pelo run_pipeline.py; rodando a etapa sozinha, é False
        baixar_historico_completo()
    else:
        atualizar()
    # a pesquisa do Banxico sai no começo do mês, fora do calendário do INEGI, então peço a cada rodada (é um pedido só)
    baixar_expectativas_banxico()
    print(f"Ingestão: {time.time() - inicio:.1f} s")
