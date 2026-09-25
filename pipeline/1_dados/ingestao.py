"""
Etapa: 1.1 Ingestao
Faz: baixa do INEGI as séries do catálogo (API BIE e app indicesdeprecios), a árvore
dos 292 genéricos com seus índices, os arquivos de ponderadores e os tabulados
oficiais CA55/CA56 (gabarito da validação), e salva tudo
intacto em data/raw com um manifesto (data e hora, sha256, observações, último
período). Dois modos: completo (histórico inteiro, reescreve data/raw) e
atualização (só roda se houve release novo; baixa a janela de sobreposição, mescla
e registra revisões).
Lê: config/catalogo_series.csv, config/calendario_releases.csv, config/parametros.py
Escreve: data/raw/ (bie/, indicesdeprecios/, arvores/, ponderadores/, tabulados/, manifesto.json, revisoes.csv)
"""

import csv
import hashlib
import html
import io
import json
import logging
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))
from config import parametros  # noqa: E402

registro = logging.getLogger("ingestao")

FONTE_BIE = "inegi_bie"
FONTE_INDICESDEPRECIOS = "inegi_indicesdeprecios"
FONTE_PONDERADORES = "inegi_ponderadores"
FONTE_TABULADOS = "inegi_tabulados"
MESES_EXPORTADOR = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
                    "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}
PADRAO_PERIODO_EXPORTADOR = re.compile(r"^(?:([12])Q )?(" + "|".join(MESES_EXPORTADOR) + r") (\d{4})$")
PADRAO_PERIODO_BIE = re.compile(r"^(\d{4})/(\d{2})(?:/0?([12]))?$")
VALORES_AUSENTES = {"", "N/E", "ND", "NA", "N/D"}
COLUNAS_REVISOES = ["fonte", "id_serie", "periodo", "valor_antigo", "valor_novo", "data_deteccao"]

_token_em_uso = None


def obter_token():
    """Não recebe nada; devolve o INEGI_TOKEN (via config/parametros.py), guardado em memória para poder ocultá-lo nos logs."""
    global _token_em_uso
    if _token_em_uso is None:
        _token_em_uso = parametros.obter_token_inegi()
    return _token_em_uso


def ocultar_token(texto):
    """Recebe um texto qualquer; devolve o texto com o token trocado por [token]."""
    texto = str(texto)
    return texto.replace(_token_em_uso, "[token]") if _token_em_uso else texto


def agora_cidade_do_mexico():
    """Não recebe nada; devolve a data e hora atuais no fuso da Cidade do México."""
    return datetime.now(ZoneInfo(parametros.FUSO_HORARIO))


def ler_catalogo():
    """Não recebe nada; devolve a lista de séries (dicionários) de config/catalogo_series.csv."""
    with open(parametros.ARQUIVO_CATALOGO, encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def ler_calendario():
    """Não recebe nada; devolve os releases de config/calendario_releases.csv, cada um com o momento da divulgação no fuso local."""
    releases = []
    with open(parametros.ARQUIVO_CALENDARIO, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            momento = datetime.fromisoformat(f"{linha['data_divulgacao']}T{linha['hora_local']}").replace(tzinfo=ZoneInfo(linha["fuso"]))
            releases.append({**linha, "momento": momento})
    return sorted(releases, key=lambda release: release["momento"])


def ler_manifesto(pasta_raw):
    """Recebe a pasta raw; devolve o manifesto.json como dicionário, ou None se ainda não existir."""
    caminho = pasta_raw / parametros.NOME_MANIFESTO
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def normalizar_periodo(texto):
    """Recebe um período do exportador ('Ago 2026', '1Q Sep 2026') ou do BIE ('2026/08', '2026/09/01'); devolve 'AAAA-MM' ou 'AAAA-MM-Q'."""
    texto = texto.strip()
    encontrado = PADRAO_PERIODO_EXPORTADOR.match(texto)
    if encontrado:
        quinzena, mes, ano = encontrado.groups()
        return f"{ano}-{MESES_EXPORTADOR[mes]:02d}" + (f"-{quinzena}" if quinzena else "")
    encontrado = PADRAO_PERIODO_BIE.match(texto)
    if encontrado:
        ano, mes, quinzena = encontrado.groups()
        return f"{ano}-{mes}" + (f"-{quinzena}" if quinzena else "")
    raise ValueError(f"Período em formato desconhecido: {texto!r}")


def periodos_esperados_do_release(release):
    """Recebe um release do calendário; devolve a lista de (frequencia, periodo normalizado) que ele publica."""
    referencia = release["periodo_referencia"]
    if release["tipo"] == "1a_quinzena":
        return [("quinzenal", f"{referencia}-1")]
    return [("mensal", referencia), ("quinzenal", f"{referencia}-2")]


def periodos_da_base(manifesto):
    """Recebe o manifesto; devolve, por frequência, o menor último período entre os arquivos principais do app (o que a base garante ter)."""
    ultimos = {}
    for entrada in manifesto.get("arquivos", {}).values():
        if entrada["fonte"] == FONTE_INDICESDEPRECIOS and entrada.get("tipo_arquivo") == "series" and entrada.get("ultimo_periodo"):
            frequencia = entrada["frequencia"]
            ultimos[frequencia] = min(ultimos.get(frequencia, entrada["ultimo_periodo"]), entrada["ultimo_periodo"])
    return ultimos


def verificar_se_ha_release_novo(manifesto, calendario, agora):
    """Recebe o manifesto, o calendário e o momento atual; devolve os releases já ocorridos (06:00 CDMX) cujo período ainda não está na base."""
    base = periodos_da_base(manifesto)
    pendentes = []
    for release in calendario:
        if release["momento"] > agora:
            continue
        faltam = [(frequencia, periodo) for frequencia, periodo in periodos_esperados_do_release(release)
                  if base.get(frequencia, "") < periodo]
        if faltam:
            pendentes.append({**release, "faltam": faltam})
    return pendentes


def requisitar(metodo, url, descricao, cabecalhos_extras=None, **argumentos):
    """Recebe método HTTP, URL, descrição curta e argumentos do requests; devolve a resposta, com pausa e retentativas exponenciais em falhas de rede ou 5xx."""
    cabecalhos = {**parametros.CABECALHOS_HTTP, **(cabecalhos_extras or {})}
    for tentativa in range(parametros.NUMERO_TENTATIVAS):
        time.sleep(parametros.PAUSA_ENTRE_CHAMADAS_SEGUNDOS)
        motivo = None
        try:
            resposta = requests.request(metodo, url, headers=cabecalhos,
                                        timeout=parametros.TEMPO_LIMITE_SEGUNDOS, **argumentos)
            if resposta.status_code < 500 and resposta.status_code != 429:
                return resposta
            motivo = f"HTTP {resposta.status_code}"
        except requests.exceptions.RequestException as erro:
            motivo = type(erro).__name__
        if tentativa < parametros.NUMERO_TENTATIVAS - 1:
            espera = parametros.ESPERAS_ENTRE_TENTATIVAS_SEGUNDOS[tentativa]
            registro.warning("  %s: falhou (%s), nova tentativa em %s s", descricao, motivo, espera)
            time.sleep(espera)
    raise RuntimeError(ocultar_token(f"{descricao}: falhou após {parametros.NUMERO_TENTATIVAS} tentativas ({motivo})")) from None


def calcular_sha256(caminho):
    """Recebe o caminho de um arquivo; devolve o sha256 do conteúdo em hexadecimal."""
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def registrar_no_manifesto(manifesto, pasta_raw, caminho, fonte, url, observacoes, ultimo_periodo, **extras):
    """Recebe o manifesto, a pasta raw, o arquivo salvo e seus metadados; grava a entrada do arquivo no manifesto (url sem token). Não devolve nada."""
    chave = caminho.relative_to(pasta_raw).as_posix()
    manifesto.setdefault("arquivos", {})[chave] = {
        "fonte": fonte,
        "url": ocultar_token(url),
        "baixado_em": agora_cidade_do_mexico().isoformat(timespec="seconds"),
        "sha256": calcular_sha256(caminho),
        "observacoes": observacoes,
        "ultimo_periodo": ultimo_periodo,
        **extras,
    }


def url_bie(ids, historico_completo):
    """Recebe ids e se é histórico completo; devolve a URL da API BIE (fonte BIE-BISE) com o token."""
    return parametros.URL_BIE_INDICADOR.format(ids=",".join(map(str, ids)), somente_ultimo=str(not historico_completo).lower(),
                                               token=obter_token())


def conteudo_bie_valido(resposta):
    """Recebe uma resposta HTTP da API BIE; devolve o JSON se for uma resposta válida com séries, ou None (erro, id inválido ou página HTML)."""
    if resposta.status_code != 200 or not resposta.headers.get("content-type", "").startswith("application/json"):
        return None
    conteudo = resposta.json()
    return conteudo if isinstance(conteudo, dict) and conteudo.get("Series") else None


def baixar_bie(ids, historico_completo):
    """Recebe ids do BIE e se é histórico completo; devolve {id: (Header, Series)} da API BIE, em lotes, repetindo id a id quando um lote falha."""
    respostas = {}
    tamanho = parametros.MAXIMO_IDS_POR_CHAMADA_BIE
    for inicio in range(0, len(ids), tamanho):
        lote = ids[inicio:inicio + tamanho]
        resposta = requisitar("GET", url_bie(lote, historico_completo), f"BIE lote de {len(lote)} ids")
        conteudo = conteudo_bie_valido(resposta)
        if conteudo:
            for serie in conteudo["Series"]:
                respostas[serie["INDICADOR"]] = (conteudo["Header"], serie)
            continue
        registro.warning("  BIE: lote de %d ids falhou (HTTP %d, %s); testando id a id", len(lote), resposta.status_code,
                         resposta.headers.get("content-type", "?"))
        for identificador in lote:
            resposta = requisitar("GET", url_bie([identificador], historico_completo), f"BIE id {identificador}")
            conteudo = conteudo_bie_valido(resposta)
            if conteudo:
                respostas[conteudo["Series"][0]["INDICADOR"]] = (conteudo["Header"], conteudo["Series"][0])
            else:
                registro.warning("  BIE: id %s inválido ou indisponível (HTTP %d); ignorado", identificador, resposta.status_code)
    return respostas


def valor_numerico(texto):
    """Recebe um valor como texto (BIE ou exportador); devolve float, ou None se ausente."""
    if texto is None or str(texto).strip() in VALORES_AUSENTES:
        return None
    return float(texto)


def valores_da_serie_bie(serie):
    """Recebe uma série do JSON do BIE; devolve {periodo normalizado: valor} só com valores presentes."""
    return {normalizar_periodo(observacao["TIME_PERIOD"]): valor_numerico(observacao["OBS_VALUE"])
            for observacao in serie["OBSERVATIONS"] if valor_numerico(observacao["OBS_VALUE"]) is not None}


def comparar_valores(fonte, id_serie, antigos, novos, data_deteccao):
    """Recebe fonte, id e dicionários {periodo: valor} antigo e novo; devolve a lista de revisões (valores que mudaram além da tolerância)."""
    return [{"fonte": fonte, "id_serie": id_serie, "periodo": periodo, "valor_antigo": antigos[periodo],
             "valor_novo": novos[periodo], "data_deteccao": data_deteccao}
            for periodo in sorted(set(antigos) & set(novos))
            if abs(antigos[periodo] - novos[periodo]) > parametros.TOLERANCIA_REVISAO]


def salvar_bie(respostas, catalogo_bie, pasta_raw, manifesto, historico_completo):
    """Recebe as respostas do BIE e as linhas do catálogo; salva data/raw/bie/<id>.json, registra no manifesto e devolve as revisões detectadas."""
    revisoes = []
    data_deteccao = agora_cidade_do_mexico().isoformat(timespec="seconds")
    frequencia_por_id = {linha["id_serie"]: linha["frequencia"] for linha in catalogo_bie}
    for identificador, (cabecalho, serie) in respostas.items():
        caminho = pasta_raw / "bie" / f"{identificador}.json"
        novos = valores_da_serie_bie(serie)
        if caminho.exists():
            antigos = valores_da_serie_bie(json.loads(caminho.read_text(encoding="utf-8"))["Series"][0])
            revisoes += comparar_valores(FONTE_BIE, identificador, antigos, novos, data_deteccao)
        caminho.write_text(json.dumps({"Header": cabecalho, "Series": [serie]}, ensure_ascii=False), encoding="utf-8")
        registrar_no_manifesto(manifesto, pasta_raw, caminho, FONTE_BIE, url_bie([identificador], historico_completo),
                               len(novos), max(novos) if novos else None, tipo_arquivo="series",
                               frequencia=frequencia_por_id.get(identificador), series=[identificador])
    return revisoes


def analisar_nos_html(texto_html):
    """Recebe o HTML de nós devolvido pelo serviço ASMX; devolve a lista de nós (id_no, nome, id_serie, tem_filhos)."""
    nos = []
    for linha in re.findall(r"(?s)<tr .*?</tr>", texto_html or ""):
        id_no = re.search(r"data-id=(\d+)", linha).group(1)
        nome = re.search(r'data-title="([^"]*)"', linha) or re.search(r"(?s)inline-block'>(.*?)</div>", linha)
        serie = re.search(r"value='(\d+)'", linha)
        nos.append({"id_no": id_no,
                    "nome": html.unescape(re.sub(r"<[^>]+>", "", nome.group(1))).strip() if nome else "",
                    "id_serie": serie.group(1) if serie else None,
                    "tem_filhos": "glyphicon-plus" in linha})
    return nos


def chamar_arvore(metodo, carga, descricao):
    """Recebe o método ASMX, a carga JSON e uma descrição; devolve o HTML de nós que o serviço de árvore do app indicesdeprecios responde."""
    resposta = requisitar("POST", parametros.URL_ARVORE_INDICESDEPRECIOS + metodo, descricao,
                          data=json.dumps(carga).encode("utf-8"), cabecalhos_extras={"Content-Type": "application/json; charset=utf-8"})
    if resposta.status_code != 200:
        raise RuntimeError(f"{descricao}: HTTP {resposta.status_code}")
    return resposta.json().get("d") or ""


def obter_filhos_completos(estrutura, id_no, nivel):
    """Recebe estrutura, nó e nível dos filhos; devolve os filhos do nó no serviço ASMX, repetindo a chamada quando o servidor omite ids de série."""
    for tentativa in range(parametros.NUMERO_TENTATIVAS):
        filhos = analisar_nos_html(chamar_arvore("ObtieneNodosV2", {"sigNivel": str(nivel), "idNodo": id_no, "esquemaBD": "", "paramfuente": "",
                                                                   "paramEstructura": estrutura, "notas": [], "open": False},
                                                 f"árvore {estrutura} nó {id_no}"))
        sem_serie = sum(1 for filho in filhos if not filho["id_serie"])
        if not sem_serie:
            return filhos
        if tentativa < parametros.NUMERO_TENTATIVAS - 1:
            espera = parametros.ESPERAS_ENTRE_TENTATIVAS_SEGUNDOS[tentativa]
            registro.warning("  árvore %s nó %s: %d filho(s) sem id de série, nova tentativa em %s s", estrutura, id_no, sem_serie, espera)
            time.sleep(espera)
    registro.warning("  árvore %s nó %s: %d filho(s) seguem sem id de série após %d tentativas", estrutura, id_no, sem_serie,
                     parametros.NUMERO_TENTATIVAS)
    return filhos


def percorrer_arvore(estrutura, no_raiz):
    """Recebe estrutura e nó raiz; percorre o serviço ASMX do app indicesdeprecios e devolve a lista de nós (ids, nomes, pais, nível)."""
    raizes = analisar_nos_html(chamar_arvore("EstructuraInicialV2", {"idEstructura": estrutura, "esquemaBD": "", "paramFuente": "",
                                                                     "notas": [], "open": False}, f"árvore {estrutura} raiz"))
    raiz = next((no for no in raizes if no["id_no"] == no_raiz), None)
    if raiz is None:
        raise RuntimeError(f"Nó raiz {no_raiz} não encontrado na estrutura {estrutura}")
    nos = [{**raiz, "id_pai": None, "nivel": 0}]
    pilha = [(no_raiz, 1)]
    while pilha:
        id_no, nivel = pilha.pop()
        filhos = obter_filhos_completos(estrutura, id_no, nivel)
        for filho in filhos:
            nos.append({**filho, "id_pai": id_no, "nivel": nivel})
            if filho["tem_filhos"]:
                pilha.append((filho["id_no"], nivel + 1))
    return nos


def contar_arvore(nos):
    """Recebe os nós de uma árvore; devolve (nós com id de série, genéricos com id de série), genérico = nome começando com código de 3 dígitos."""
    com_serie = sum(1 for no in nos if no["id_serie"])
    genericos = sum(1 for no in nos if no["id_serie"] and re.match(r"^\d{3} ", no["nome"]))
    return com_serie, genericos


def varrer_arvore_genericos(estrutura, no_raiz, frequencia, pasta_raw, manifesto):
    """Recebe estrutura e nó raiz da árvore por objeto do gasto; varre o serviço ASMX até obter a árvore completa, salva data/raw/arvores/<estrutura>.json e devolve os nós."""
    esperado = (parametros.NUMERO_NOS_COM_SERIE_ESPERADO, parametros.NUMERO_GENERICOS_ESPERADO)
    for tentativa in range(1, parametros.TENTATIVAS_VARREDURA_ARVORE + 1):
        nos = percorrer_arvore(estrutura, no_raiz)
        obtido = contar_arvore(nos)
        if obtido == esperado:
            break
        registro.warning("  árvore %s: incompleta na tentativa %d (%d nós com série, %d genéricos; esperado %d e %d)",
                         estrutura, tentativa, *obtido, *esperado)
    else:
        raise RuntimeError(f"Árvore {estrutura} ({frequencia}) incompleta após {parametros.TENTATIVAS_VARREDURA_ARVORE} varreduras: "
                           f"{obtido[0]} nós com série e {obtido[1]} genéricos (esperado {esperado[0]} e {esperado[1]}). Nada foi salvo.")
    caminho = pasta_raw / "arvores" / f"{estrutura}.json"
    documento = {"estrutura": estrutura, "frequencia": frequencia, "no_raiz": no_raiz, "nos": nos}
    caminho.write_text(json.dumps(documento, ensure_ascii=False, indent=1), encoding="utf-8")
    com_serie = sum(1 for no in nos if no["id_serie"])
    registrar_no_manifesto(manifesto, pasta_raw, caminho, FONTE_INDICESDEPRECIOS, parametros.URL_ARVORE_INDICESDEPRECIOS + "ObtieneNodosV2",
                           com_serie, None, tipo_arquivo="arvore", frequencia=frequencia, estrutura=estrutura)
    return nos


def ler_csv_exportador(texto):
    """Recebe o texto de um CSV do exportador do app; devolve a tabela (prefácio, títulos, cifras, ids e linhas por período)."""
    linhas_texto = texto.splitlines()
    inicio = next((indice for indice, linha in enumerate(linhas_texto) if linha.startswith('"Título"')), None)
    if inicio is None:
        raise ValueError("CSV do exportador sem a linha 'Título'")
    tabela = {"prefacio": linhas_texto[:inicio], "titulos": [], "cifras": [], "ids": [], "linhas": {}}
    for linha in csv.reader(io.StringIO("\n".join(linhas_texto[inicio:]))):
        if not linha:
            continue
        if linha[0] == "Título":
            tabela["titulos"] = linha[1:]
        elif linha[0] == "Cifra":
            tabela["cifras"] = linha[1:]
        elif linha[0] == "Fecha":
            tabela["ids"] = [valor.strip() for valor in linha[1:] if valor.strip()]
        elif PADRAO_PERIODO_EXPORTADOR.match(linha[0].strip()):
            tabela["linhas"][linha[0].strip()] = linha[1:1 + len(tabela["ids"])]
    if not tabela["ids"]:
        raise ValueError("CSV do exportador sem a linha 'Fecha' com os ids")
    return tabela


def combinar_lotes(tabelas):
    """Recebe as tabelas de vários lotes do exportador; devolve uma tabela única com as colunas lado a lado, na ordem dos lotes."""
    combinada = {"prefacio": tabelas[0]["prefacio"], "titulos": [], "cifras": [], "ids": [], "linhas": {}}
    rotulos = []
    for tabela in tabelas:
        rotulos += [rotulo for rotulo in tabela["linhas"] if rotulo not in rotulos]
    for tabela in tabelas:
        largura = len(tabela["ids"])
        combinada["titulos"] += (tabela["titulos"] + [""] * largura)[:largura]
        combinada["cifras"] += (tabela["cifras"] + [""] * largura)[:largura]
        combinada["ids"] += tabela["ids"]
        for rotulo in rotulos:
            combinada["linhas"].setdefault(rotulo, []).extend(tabela["linhas"].get(rotulo, [""] * largura))
    return combinada


def exportar_indicesdeprecios(ids, ano_inicio, ano_fim, estrutura):
    """Recebe ids, anos e estrutura do app indicesdeprecios; devolve (tabela combinada, bytes originais se veio num único lote) via POST no exportador CSV."""
    tabelas, conteudos = [], []
    tamanho = parametros.MAXIMO_IDS_POR_EXPORTACAO
    for inicio in range(0, len(ids), tamanho):
        lote = ids[inicio:inicio + tamanho]
        formulario = {**parametros.CAMPOS_FIXOS_EXPORTADOR, "idEstructura": estrutura, "cuadro": estrutura, "cvEstructura": estrutura,
                      "_anioI": str(ano_inicio), "_anioF": str(ano_fim), "_series": "c|" + ",".join(map(str, lote)) + ","}
        resposta = requisitar("POST", parametros.URL_EXPORTADOR_INDICESDEPRECIOS, f"exportador {estrutura} lote de {len(lote)} ids", data=formulario)
        if resposta.status_code != 200 or "csv" not in resposta.headers.get("content-type", ""):
            raise RuntimeError(f"exportador {estrutura}: resposta inesperada (HTTP {resposta.status_code})")
        tabela = ler_csv_exportador(resposta.content.decode(parametros.CODIFICACAO_EXPORTADOR))
        faltando = set(map(str, lote)) - set(tabela["ids"])
        if faltando:
            raise RuntimeError(f"exportador {estrutura}: ids sem resposta: {sorted(faltando)[:10]}")
        tabelas.append(tabela)
        conteudos.append(resposta.content)
    return combinar_lotes(tabelas), (conteudos[0] if len(conteudos) == 1 else None)


def escrever_csv_exportador(tabela, caminho):
    """Recebe uma tabela no formato do exportador e o caminho; grava o CSV no mesmo layout (cp1252, CRLF, campos entre aspas). Não devolve nada."""
    saida = io.StringIO()
    escritor = csv.writer(saida, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    escritor.writerow(["Título", *tabela["titulos"]])
    escritor.writerow(["Cifra", *tabela["cifras"]])
    escritor.writerow(["Fecha", *tabela["ids"]])
    for rotulo, valores in tabela["linhas"].items():
        escritor.writerow([rotulo, *valores])
    texto = "\r\n".join(tabela["prefacio"]) + "\r\n" + saida.getvalue()
    caminho.write_bytes(texto.encode(parametros.CODIFICACAO_EXPORTADOR, errors="replace"))


def resumir_tabela(tabela):
    """Recebe uma tabela do exportador; devolve (número de observações presentes, último período normalizado com dado)."""
    observacoes, ultimo = 0, None
    for rotulo, valores in tabela["linhas"].items():
        presentes = sum(1 for valor in valores if valor_numerico(valor) is not None)
        observacoes += presentes
        if presentes:
            ultimo = max(ultimo or "", normalizar_periodo(rotulo))
    return observacoes, ultimo


def mesclar_exportacao(antiga, nova, data_deteccao):
    """Recebe a tabela existente e a da janela nova; devolve (tabela mesclada, revisões, períodos novos, observações novas)."""
    if set(antiga["ids"]) != set(nova["ids"]):
        raise RuntimeError("As séries da janela não coincidem com as do arquivo existente; rode o modo completo.")
    posicao_nova = {identificador: indice for indice, identificador in enumerate(nova["ids"])}
    revisoes, periodos_novos, observacoes_novas = [], [], 0
    for rotulo, valores_novos in nova["linhas"].items():
        alinhados = [valores_novos[posicao_nova[identificador]] for identificador in antiga["ids"]]
        if rotulo not in antiga["linhas"]:
            antiga["linhas"][rotulo] = alinhados
            periodos_novos.append(normalizar_periodo(rotulo))
            observacoes_novas += sum(1 for valor in alinhados if valor_numerico(valor) is not None)
            continue
        valores_antigos = antiga["linhas"][rotulo]
        for indice, identificador in enumerate(antiga["ids"]):
            antigo, novo = valor_numerico(valores_antigos[indice]), valor_numerico(alinhados[indice])
            if novo is None:
                continue
            if antigo is None:
                observacoes_novas += 1
            elif abs(antigo - novo) > parametros.TOLERANCIA_REVISAO:
                revisoes.append({"fonte": FONTE_INDICESDEPRECIOS, "id_serie": identificador, "periodo": normalizar_periodo(rotulo),
                                 "valor_antigo": antigo, "valor_novo": novo, "data_deteccao": data_deteccao})
            valores_antigos[indice] = alinhados[indice]
    antiga["linhas"] = dict(sorted(antiga["linhas"].items(), key=lambda item: normalizar_periodo(item[0])))
    return antiga, revisoes, periodos_novos, observacoes_novas


def salvar_exportacao(ids, estrutura, frequencia, modo, ano_atual, pasta_raw, manifesto):
    """Recebe ids, estrutura, frequência, modo e ano; exporta do app, grava ou mescla data/raw/indicesdeprecios/<estrutura>_<frequencia>.csv e devolve as revisões."""
    caminho = pasta_raw / "indicesdeprecios" / f"{estrutura}_{frequencia}.csv"
    ids = sorted(ids, key=int)
    revisoes = []
    if modo == "completo" or not caminho.exists():
        tabela, bruto = exportar_indicesdeprecios(ids, parametros.ANO_INICIAL_EXPORTADOR, ano_atual, estrutura)
        if bruto is not None:
            caminho.write_bytes(bruto)
        else:
            escrever_csv_exportador(tabela, caminho)
        detalhe = "histórico completo"
    else:
        ano_inicio = ano_atual - parametros.JANELA_SOBREPOSICAO_ANOS + 1
        nova, _ = exportar_indicesdeprecios(ids, ano_inicio, ano_atual, estrutura)
        antiga = ler_csv_exportador(caminho.read_bytes().decode(parametros.CODIFICACAO_EXPORTADOR))
        data_deteccao = agora_cidade_do_mexico().isoformat(timespec="seconds")
        tabela, revisoes, periodos_novos, observacoes_novas = mesclar_exportacao(antiga, nova, data_deteccao)
        escrever_csv_exportador(tabela, caminho)
        detalhe = (f"janela {ano_inicio}-{ano_atual}: {len(periodos_novos)} período(s) novo(s) {periodos_novos}, "
                   f"{observacoes_novas} observação(ões) nova(s), {len(revisoes)} revisão(ões)")
    observacoes, ultimo = resumir_tabela(tabela)
    registrar_no_manifesto(manifesto, pasta_raw, caminho, FONTE_INDICESDEPRECIOS, parametros.URL_EXPORTADOR_INDICESDEPRECIOS,
                           observacoes, ultimo, tipo_arquivo="series", frequencia=frequencia, estrutura=estrutura, series=tabela["ids"])
    registro.info("  %s_%s: %d séries, último %s (%s)", estrutura, frequencia, len(tabela["ids"]), ultimo, detalhe)
    return revisoes


def baixar_ponderadores(pasta_raw, manifesto, forcar):
    """Recebe a pasta raw, o manifesto e se deve forçar; baixa os xlsx de ponderadores do INEGI (2024 e 2018) se faltarem ou se forçado. Não devolve nada."""
    for nome, url in parametros.URLS_PONDERADORES.items():
        caminho = pasta_raw / "ponderadores" / nome
        if caminho.exists() and not forcar:
            continue
        resposta = requisitar("GET", url, f"ponderadores {nome}")
        if resposta.status_code != 200 or not resposta.content.startswith(b"PK"):
            raise RuntimeError(f"ponderadores {nome}: resposta inesperada (HTTP {resposta.status_code})")
        caminho.write_bytes(resposta.content)
        registrar_no_manifesto(manifesto, pasta_raw, caminho, FONTE_PONDERADORES, url, None, None, tipo_arquivo="ponderadores")
        registro.info("  %s: %d KB", nome, len(resposta.content) // 1024)


def baixar_tabulados(pasta_raw, manifesto):
    """Recebe a pasta raw e o manifesto; baixa os tabulados oficiais CA55/CA56 (período atual e anterior) do wsDataService do INEGI em data/raw/tabulados/. Não devolve nada."""
    for frequencia, cuadro in parametros.TABULADOS_OFICIAIS.items():
        for rotulo, esquema in parametros.ESQUEMAS_TABULADO.items():
            url = parametros.URL_TABULADO_INPC.format(cuadro=cuadro, esquema=esquema)
            resposta = requisitar("GET", url, f"tabulado {cuadro} esquema {esquema}")
            conteudo = resposta.json() if resposta.status_code == 200 else None
            if not conteudo or not conteudo.get("Datos") or not conteudo.get("Encab"):
                raise RuntimeError(f"tabulado {cuadro} esquema {esquema}: resposta inesperada (HTTP {resposta.status_code})")
            caminho = pasta_raw / "tabulados" / f"{cuadro}_esquema{esquema}.json"
            caminho.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
            periodo = normalizar_periodo(conteudo["Encab"][0]["periodo_actual"])
            registrar_no_manifesto(manifesto, pasta_raw, caminho, FONTE_TABULADOS, url, len(conteudo["Datos"]), periodo,
                                   tipo_arquivo="tabulado", frequencia=frequencia, cuadro=cuadro, esquema=esquema, papel=rotulo)
            registro.info("  %s esquema %d (%s): %d linhas, período %s", cuadro, esquema, rotulo, len(conteudo["Datos"]), periodo)


def registrar_revisoes(revisoes, pasta_raw):
    """Recebe a lista de revisões e a pasta raw; acrescenta as linhas em data/raw/revisoes.csv (cria o arquivo só se houver revisões). Não devolve nada."""
    if not revisoes:
        return
    caminho = pasta_raw / parametros.NOME_REVISOES
    novo = not caminho.exists()
    with open(caminho, "a", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_REVISOES, lineterminator="\n")
        if novo:
            escritor.writeheader()
        escritor.writerows(revisoes)


def ultimos_releases_ocorridos(calendario, agora):
    """Recebe o calendário e o momento atual; devolve o último release já ocorrido de cada tipo."""
    ultimos = {}
    for release in calendario:
        if release["momento"] <= agora:
            ultimos[release["tipo"]] = release
    return list(ultimos.values())


def conferir_periodos_esperados(manifesto, releases):
    """Recebe o manifesto e os releases a conferir; devolve a lista de (frequencia, periodo) esperados que ainda não chegaram à base."""
    base = periodos_da_base(manifesto)
    return sorted({(frequencia, periodo) for release in releases for frequencia, periodo in periodos_esperados_do_release(release)
                   if base.get(frequencia, "") < periodo})


def resumir_base(manifesto):
    """Recebe o manifesto; devolve (número de arquivos, número de séries, {fonte e frequência: último período})."""
    arquivos = manifesto.get("arquivos", {})
    series = sum(len(entrada.get("series", [])) for entrada in arquivos.values())
    ultimos = {}
    for entrada in arquivos.values():
        if entrada.get("ultimo_periodo"):
            chave = f"{entrada['fonte']} {entrada.get('frequencia')}"
            ultimos[chave] = max(ultimos.get(chave, ""), entrada["ultimo_periodo"])
    return len(arquivos), series, ultimos


def executar(modo):
    """Recebe o modo ('completo' ou 'atualizacao'); orquestra a ingestão e devolve um resumo com o status (ja_atualizado, atualizado ou atrasado)."""
    inicio_total = time.time()
    agora = agora_cidade_do_mexico()
    calendario = ler_calendario()
    manifesto_atual = ler_manifesto(parametros.PASTA_RAW)

    if modo == "atualizacao" and manifesto_atual is None:
        registro.info("Base vazia: executando o modo completo.")
        modo = "completo"
    if modo == "atualizacao":
        pendentes = verificar_se_ha_release_novo(manifesto_atual, calendario, agora)
        if not pendentes:
            ultimo = manifesto_atual.get("ultimo_release_incorporado") or {}
            registro.info("Já atualizado: nenhum release novo desde %s (%s). Nenhuma chamada à rede.",
                          ultimo.get("data_divulgacao", "?"), ultimo.get("tipo", "?"))
            return {"status": "ja_atualizado", "modo": modo}
        for release in pendentes:
            registro.info("Release pendente: %s %s (ref. %s), faltam %s", release["data_divulgacao"], release["tipo"],
                          release["periodo_referencia"], release["faltam"])
        pasta_raw, manifesto, releases_a_conferir = parametros.PASTA_RAW, manifesto_atual, pendentes
    else:
        pasta_raw = parametros.PASTA_RAW_EM_CONSTRUCAO
        if pasta_raw.exists():
            shutil.rmtree(pasta_raw)
        manifesto, releases_a_conferir = {"arquivos": {}}, ultimos_releases_ocorridos(calendario, agora)
    parametros.criar_pastas(pasta_raw)
    registro.info("Ingestão em modo %s", modo)

    catalogo = ler_catalogo()
    ano_atual = agora.year
    revisoes = []

    inicio = time.time()
    catalogo_bie = [linha for linha in catalogo if linha["fonte"] == FONTE_BIE]
    respostas = baixar_bie([linha["id_serie"] for linha in catalogo_bie], historico_completo=True)
    revisoes += salvar_bie(respostas, catalogo_bie, pasta_raw, manifesto, historico_completo=True)
    registro.info("BIE: %d de %d séries (histórico completo) em %.1f s", len(respostas), len(catalogo_bie), time.time() - inicio)

    inicio = time.time()
    catalogo_app = [linha for linha in catalogo if linha["fonte"] == FONTE_INDICESDEPRECIOS]
    for (tipo, frequencia), estrutura in parametros.ESTRUTURAS_CATALOGO.items():
        ids = [linha["id_serie"] for linha in catalogo_app if linha["tipo"] == tipo and linha["frequencia"] == frequencia]
        if ids:
            revisoes += salvar_exportacao(ids, estrutura, frequencia, modo, ano_atual, pasta_raw, manifesto)
    registro.info("App indicesdeprecios, séries do catálogo: %.1f s", time.time() - inicio)

    for frequencia, configuracao in parametros.ARVORES_GENERICOS.items():
        inicio = time.time()
        estrutura = configuracao["estrutura"]
        caminho_arvore = pasta_raw / "arvores" / f"{estrutura}.json"
        if modo == "completo" or not caminho_arvore.exists():
            nos = varrer_arvore_genericos(estrutura, configuracao["no_raiz"], frequencia, pasta_raw, manifesto)
            registro.info("  árvore %s (%s): %d nós varridos, %d com série, %d genéricos, em %.1f s", estrutura, frequencia, len(nos),
                          sum(1 for no in nos if no["id_serie"]), sum(1 for no in nos if no["id_serie"] and re.match(r"^\d{3} ", no["nome"])),
                          time.time() - inicio)
        else:
            nos = json.loads(caminho_arvore.read_text(encoding="utf-8"))["nos"]
        ids = [no["id_serie"] for no in nos if no["id_serie"]]
        revisoes += salvar_exportacao(ids, estrutura, frequencia, modo, ano_atual, pasta_raw, manifesto)
        registro.info("App indicesdeprecios, genéricos %s: %.1f s", frequencia, time.time() - inicio)

    inicio = time.time()
    baixar_ponderadores(pasta_raw, manifesto, forcar=(modo == "completo"))
    registro.info("Ponderadores: %.1f s", time.time() - inicio)

    inicio = time.time()
    baixar_tabulados(pasta_raw, manifesto)
    registro.info("Tabulados oficiais: %.1f s", time.time() - inicio)

    registrar_revisoes(revisoes, pasta_raw)
    if revisoes:
        registro.warning("Revisões detectadas: %d (registradas em %s)", len(revisoes), parametros.NOME_REVISOES)

    faltantes = conferir_periodos_esperados(manifesto, releases_a_conferir)
    if faltantes:
        status = "atrasado"
        registro.warning("ATENÇÃO: o INEGI ainda não publicou %s. A base NÃO foi marcada como atualizada; rode de novo mais tarde.", faltantes)
    else:
        status = "atualizado"
        ultimo = max(releases_a_conferir, key=lambda release: release["momento"])
        manifesto["ultimo_release_incorporado"] = {chave: ultimo[chave] for chave in ("data_divulgacao", "tipo", "periodo_referencia")}
    manifesto["modo_ultima_execucao"] = modo
    manifesto["gerado_em"] = agora_cidade_do_mexico().isoformat(timespec="seconds")
    (pasta_raw / parametros.NOME_MANIFESTO).write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")

    if modo == "completo":
        if parametros.PASTA_RAW.exists():
            shutil.rmtree(parametros.PASTA_RAW)
        pasta_raw.rename(parametros.PASTA_RAW)

    arquivos, series, ultimos = resumir_base(manifesto)
    registro.info("Concluído (%s) em %.1f s: %d arquivos, %d séries em data/raw", status, time.time() - inicio_total, arquivos, series)
    for chave, periodo in sorted(ultimos.items()):
        registro.info("  último período %s: %s", chave, periodo)
    return {"status": status, "modo": modo, "arquivos": arquivos, "series": series, "ultimos_periodos": ultimos, "revisoes": len(revisoes)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    modo_pedido = globals().get("modo_execucao") or ("completo" if "--completo" in sys.argv else "atualizacao")
    resultado_ingestao = executar(modo_pedido)
