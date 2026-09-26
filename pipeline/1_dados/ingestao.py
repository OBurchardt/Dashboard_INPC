# Etapa 1.1: Ingestão
# Baixa do INEGI tudo o que o dashboard usa e guarda em data/raw, em arquivos que abrem no Excel:
# uma tabela por conjunto de séries (uma linha por período, uma coluna por id da série).
# Fontes: o app "indicesdeprecios" (componentes, incidências e os 292 genéricos), os xlsx de
# ponderadores e os tabulados oficiais do último release (gabarito da validação).
# Dois modos: o histórico completo (IMPORTAR_DO_ZERO no run_pipeline.py, ou base muito atrasada) e a
# atualização do dia a dia, que só vai à rede se o calendário diz que saiu dado novo, e então
# rebaixa uma janela curta e sobrescreve esses períodos na base.

import csv
import io
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para a etapa rodar sozinha: a raiz do projeto entra no caminho do Python
from config import parametros as p

MESES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}


# ==== 1. Rede ====
def pedir(metodo, url, **argumentos):
    """Faz a chamada HTTP com algumas tentativas, porque o servidor do INEGI derruba conexões."""
    for tentativa in range(1, p.TENTATIVAS_REDE + 1):
        try:
            resposta = requests.request(metodo, url, timeout=p.TEMPO_LIMITE_SEGUNDOS, headers={"User-Agent": "Mozilla/5.0"}, **argumentos)
            resposta.raise_for_status()
            return resposta
        except requests.RequestException:
            if tentativa == p.TENTATIVAS_REDE:
                raise
            time.sleep(5 * tentativa)


# ==== 2. Períodos ====
def periodo_padrao(rotulo):
    """Converte o rótulo do INEGI ('Ago 2026' ou '1Q Sep 2026') em '2026-08' ou '2026-09-Q1'."""
    partes = rotulo.split()
    quinzena = f"-Q{partes[0][0]}" if len(partes) == 3 else ""
    return f"{partes[-1]}-{MESES[partes[-2]]:02d}{quinzena}"


def mes_do_periodo(periodo):
    """Número sequencial do mês de um período ('2026-08' ou '2026-08-Q2'), para contar meses de atraso."""
    return int(periodo[:4]) * 12 + int(periodo[5:7]) - 1


# ==== 3. Árvore dos genéricos ====
def filhos_do_no(estrutura, id_no, nivel):
    """Pede ao serviço de árvore do app os filhos de um nó; cada linha HTML traz o id do nó, o nome e o id da série."""
    carga = {"sigNivel": str(nivel), "idNodo": id_no, "esquemaBD": "", "paramfuente": "",
             "paramEstructura": estrutura, "notas": [], "open": False}
    html = pedir("POST", p.URL_ARVORE, json=carga).json()["d"]
    filhos = []
    for linha in re.findall(r"(?s)<tr .*?</tr>", html):
        serie = re.search(r"value='(\d+)'", linha)
        nome = re.search(r'data-title="([^"]*)"', linha).group(1)
        filhos.append({"id_no": re.search(r"data-id=(\d+)", linha).group(1), "nome": nome,
                       "id_serie": serie.group(1) if serie else None,
                       "generico": bool(serie) and bool(re.match(r"\d{3} ", nome)),  # genérico = nome com código de 3 dígitos
                       "tem_filhos": "glyphicon-plus" in linha})
    return filhos


def varrer_arvore(estrutura, raiz):
    """Percorre a árvore do objeto do gasto a partir do nó raiz e devolve todos os nós com o id do pai."""
    nos, pendentes = [], [(raiz, 1)]
    while pendentes:
        id_no, nivel = pendentes.pop()
        for filho in filhos_do_no(estrutura, id_no, nivel):
            if filho.pop("tem_filhos"):
                pendentes.append((filho["id_no"], nivel + 1))
            nos.append({**filho, "id_pai": id_no, "nivel": nivel})
    return nos


def baixar_arvore(frequencia):
    """Salva a árvore de genéricos; o servidor às vezes omite ids, então uma árvore incompleta é varrida de novo uma vez."""
    for _ in range(2):
        nos = varrer_arvore(*p.ARVORES[frequencia])
        genericos = sum(no["generico"] for no in nos)
        if genericos == 292:  # fato: a cesta 2024 do INPC tem 292 genéricos (documento metodológico do INEGI, 2024)
            break
    else:
        raise SystemExit(f"Árvore {frequencia} veio com {genericos} de 292 genéricos; tente de novo mais tarde.")
    (p.PASTA_RAW / f"arvore_genericos_{frequencia}.json").write_text(json.dumps(nos, ensure_ascii=False, indent=1), encoding="utf-8")


# ==== 4. Séries (exportador do app) ====
def ler_csv_exportador(texto):
    """Transforma o CSV do exportador em tabela período x id; os dados começam depois da linha 'Fecha', que traz os ids."""
    linhas = list(csv.reader(io.StringIO(texto)))
    inicio = next(numero for numero, linha in enumerate(linhas) if linha and linha[0] == "Fecha")
    ids = [valor for valor in linhas[inicio][1:] if valor]
    dados = [linha for linha in linhas[inicio + 1:] if linha]
    return pd.DataFrame([linha[1:len(ids) + 1] for linha in dados], columns=ids,
                        index=pd.Index([periodo_padrao(linha[0]) for linha in dados], name="periodo"))


def exportar(estrutura, ids, ano_inicio, ano_fim):
    """Baixa as séries de uma estrutura do app entre dois anos, em lotes de ids (lotes grandes estouram o tempo)."""
    lotes = []
    for inicio in range(0, len(ids), p.LOTE_EXPORTACAO_IDS):
        formulario = {"idEstructura": estrutura, "cuadro": estrutura, "cvEstructura": estrutura, "_formato": "CSV",
                      "_tipo": "Niveles", "_orient": "vertical", "_meta": "0", "_info": "", "esquema": "", "st": "",
                      "pf": "inp", "_anioI": ano_inicio, "_anioF": ano_fim,
                      "_series": "c|" + ",".join(ids[inicio:inicio + p.LOTE_EXPORTACAO_IDS]) + ","}
        lotes.append(ler_csv_exportador(pedir("POST", p.URL_EXPORTADOR, data=formulario).content.decode("cp1252")))
    return pd.concat(lotes, axis=1)


def conjuntos_de_series():
    """Lista (arquivo, estrutura, ids) das seis tabelas: componentes, incidências e genéricos em cada frequência."""
    catalogo = pd.read_csv(p.CATALOGO, dtype=str, encoding="utf-8")
    conjuntos = []
    for (tipo, frequencia), estrutura in p.ESTRUTURAS.items():
        ids = catalogo[(catalogo["tipo"] == tipo) & (catalogo["frequencia"] == frequencia)]["id_serie"].tolist()
        nome = "componentes" if tipo == "indice" else "incidencias"
        conjuntos.append((f"{nome}_{frequencia}", estrutura, ids))
    for frequencia, (estrutura, _) in p.ARVORES.items():
        arvore = json.loads((p.PASTA_RAW / f"arvore_genericos_{frequencia}.json").read_text(encoding="utf-8"))
        conjuntos.append((f"genericos_{frequencia}", estrutura, [no["id_serie"] for no in arvore if no["generico"]]))
    return conjuntos


def salvar_tabela(nome, tabela, sobrescrever_periodos=False):
    """Grava data/raw/<nome>.csv; na atualização, os períodos baixados substituem os que a base já tinha."""
    caminho = p.PASTA_RAW / f"{nome}.csv"
    if sobrescrever_periodos:
        antiga = pd.read_csv(caminho, dtype=str, index_col="periodo", keep_default_na=False, encoding="utf-8")
        tabela = pd.concat([antiga.drop(tabela.index, errors="ignore"), tabela]).sort_index()
    tabela.to_csv(caminho, encoding="utf-8")


# ==== 5. Ponderadores e tabulados oficiais ====
def baixar_ponderadores():
    """Baixa os xlsx oficiais de ponderadores das cestas 2024 e 2018 (com a classificação de cada genérico)."""
    for nome, url in p.URLS_PONDERADORES.items():
        (p.PASTA_RAW / nome).write_bytes(pedir("GET", url).content)


def baixar_tabulados():
    """Baixa os tabulados do último release; o período vai junto em formato padrão para a validação saber o que comparar."""
    for frequencia, cuadro in p.TABULADOS.items():
        tabulado = pedir("GET", p.URL_TABULADO.format(cuadro=cuadro)).json()
        tabulado["periodo"] = periodo_padrao(tabulado["Encab"][0]["periodo_actual"])
        (p.PASTA_RAW / f"tabulado_{frequencia}.json").write_text(json.dumps(tabulado, ensure_ascii=False), encoding="utf-8")


# ==== 6. Calendário e base ====
def ultimo_divulgado():
    """Último período publicado em cada frequência, segundo os releases do calendário que já aconteceram."""
    calendario = pd.read_csv(p.CALENDARIO, dtype=str, encoding="utf-8")
    momentos = pd.to_datetime(calendario["data_divulgacao"] + " " + calendario["hora_local"]).dt.tz_localize(p.FUSO)
    ocorridos = calendario[momentos <= datetime.now(ZoneInfo(p.FUSO))]
    mensais = ocorridos[ocorridos["tipo"] == "mensal_e_2a_quinzena"]["periodo_referencia"]
    primeiras = ocorridos[ocorridos["tipo"] == "1a_quinzena"]["periodo_referencia"]
    # o release mensal traz também a 2a quinzena do mesmo mês; o outro release traz a 1a quinzena
    return {"mensal": mensais.max(), "quinzenal": max([f"{mes}-Q2" for mes in mensais] + [f"{mes}-Q1" for mes in primeiras])}


def ultimo_na_base():
    """Último período que todas as tabelas da base têm, por frequência; None se a base ainda não existe."""
    ultimos = {}
    for frequencia in ("mensal", "quinzenal"):
        arquivos = [p.PASTA_RAW / f"{nome}_{frequencia}.csv" for nome in ("componentes", "incidencias", "genericos")]
        if not all(arquivo.exists() for arquivo in arquivos):
            return None
        ultimos[frequencia] = min(pd.read_csv(arquivo, usecols=["periodo"], encoding="utf-8")["periodo"].iloc[-1] for arquivo in arquivos)
    return ultimos


# ==== 7. Os dois modos ====
def baixar_historico_completo():
    """Baixa árvores, ponderadores, todo o histórico de todas as séries e os tabulados; reescreve a base e devolve True."""
    for frequencia in p.ARVORES:
        baixar_arvore(frequencia)
    baixar_ponderadores()
    for nome, estrutura, ids in conjuntos_de_series():
        salvar_tabela(nome, exportar(estrutura, ids, 1969, datetime.now(ZoneInfo(p.FUSO)).year))  # fato: 1969 é o primeiro ano que o app oferece
    baixar_tabulados()
    print(f"Histórico completo baixado (último dado: {ultimo_na_base()})")
    return True


def avisar_se_o_calendario_acabou():
    """Avisa quando todos os releases do calendário já passaram, porque sem o ano seguinte a base congela."""
    calendario = pd.read_csv(p.CALENDARIO, dtype=str, encoding="utf-8")
    ultimo = pd.Timestamp(calendario["data_divulgacao"].max() + " " + calendario["hora_local"].iloc[-1]).tz_localize(p.FUSO)
    if datetime.now(ZoneInfo(p.FUSO)) > ultimo:
        print(f"Aviso: o calendário acaba em {ultimo:%d/%m/%Y}; acrescente o de {ultimo.year + 1} em config/calendario_releases.csv")


def atualizar():
    """Atualização do dia a dia; devolve True se a base mudou."""
    avisar_se_o_calendario_acabou()
    divulgado, base = ultimo_divulgado(), ultimo_na_base()
    if base == divulgado:
        print(f"Já atualizado (último dado: {base['mensal']} e {base['quinzenal']})")
        return False
    if base is None or max(mes_do_periodo(divulgado[f]) - mes_do_periodo(base[f]) for f in base) > p.MESES_JANELA_ATUALIZACAO:
        print("Base vazia ou muito atrasada: rodando histórico completo")
        return baixar_historico_completo()
    # o exportador filtra por ano: começa no ano do mês que fica 6 meses antes do último divulgado
    ano_inicio = (mes_do_periodo(divulgado["mensal"]) - p.MESES_JANELA_ATUALIZACAO) // 12
    for nome, estrutura, ids in conjuntos_de_series():
        salvar_tabela(nome, exportar(estrutura, ids, ano_inicio, datetime.now(ZoneInfo(p.FUSO)).year), sobrescrever_periodos=True)
    baixar_tabulados()
    print(f"Base atualizada de {base} para {ultimo_na_base()} (janela desde {ano_inicio})")
    return True


if __name__ == "__main__":
    inicio = time.time()
    baixar_historico_completo() if globals().get("importar_do_zero") else atualizar()  # a opção vem do run_pipeline.py
    print(f"Ingestão: {time.time() - inicio:.1f} s")
