"""
Parâmetros do projeto. Único módulo que todas as etapas podem ler.
Contém caminhos, token, fuso, endereços das fontes do INEGI e regras de rede
da ingestão. Parâmetros de etapas futuras entram aqui quando elas forem
implementadas.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
PASTA_CONFIG = RAIZ_PROJETO / "config"
PASTA_DATA = RAIZ_PROJETO / "data"
PASTA_RAW = PASTA_DATA / "raw"
PASTA_RAW_EM_CONSTRUCAO = PASTA_DATA / "raw_em_construcao"  # usada só durante o modo completo
PASTA_PROCESSED = PASTA_DATA / "processed"
PASTA_OUTPUT = RAIZ_PROJETO / "output"

SUBPASTAS_RAW = ("bie", "indicesdeprecios", "arvores", "ponderadores", "tabulados")
NOME_MANIFESTO = "manifesto.json"
NOME_REVISOES = "revisoes.csv"

ARQUIVO_CATALOGO = PASTA_CONFIG / "catalogo_series.csv"
ARQUIVO_CALENDARIO = PASTA_CONFIG / "calendario_releases.csv"
ARQUIVO_ENV = RAIZ_PROJETO / ".env"


def criar_pastas(pasta_raw=PASTA_RAW):
    """Recebe a pasta raw (padrão data/raw); cria ela, suas subpastas, data/processed e output se não existirem. Não devolve nada."""
    for pasta in [pasta_raw, *(pasta_raw / nome for nome in SUBPASTAS_RAW), PASTA_PROCESSED, PASTA_OUTPUT]:
        pasta.mkdir(parents=True, exist_ok=True)


criar_pastas()

# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
NOME_VARIAVEL_TOKEN_INEGI = "INEGI_TOKEN"


def obter_token_inegi():
    """Não recebe nada; devolve o token INEGI_TOKEN lido do .env (python-dotenv). Erro claro se faltar, sem mostrar valor."""
    load_dotenv(ARQUIVO_ENV)
    token = os.getenv(NOME_VARIAVEL_TOKEN_INEGI, "").strip()
    if not token:
        raise RuntimeError(f"Variável {NOME_VARIAVEL_TOKEN_INEGI} ausente ou vazia no arquivo .env da raiz do projeto.")
    return token


# ---------------------------------------------------------------------------
# Tempo
# ---------------------------------------------------------------------------
FUSO_HORARIO = "America/Mexico_City"

# ---------------------------------------------------------------------------
# Fontes do INEGI
# ---------------------------------------------------------------------------
# API do Banco de Indicadores (BIE); a fonte que responde é BIE-BISE.
# {somente_ultimo}: "false" = histórico completo, "true" = só o último dado.
URL_BIE_INDICADOR = (
    "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/"
    "INDICATOR/{ids}/es/00/{somente_ultimo}/BIE-BISE/2.0/{token}?type=json"
)

# App indicesdeprecios: árvore (serviço ASMX) e exportador CSV (POST de formulário).
URL_ARVORE_INDICESDEPRECIOS = "https://www.inegi.org.mx/app/indicesdeprecios/servicios/ArbolAjaxInteraccion.asmx/"
URL_EXPORTADOR_INDICESDEPRECIOS = "https://www.inegi.org.mx/app/indicesdeprecios/Exportacion.aspx?INPtipoExporta=CSV"
CODIFICACAO_EXPORTADOR = "cp1252"
CAMPOS_FIXOS_EXPORTADOR = {
    "_formato": "CSV",
    "_meta": "0",
    "_tipo": "Niveles",
    "_info": "",
    "_orient": "vertical",
    "esquema": "",
    "st": "",
    "pf": "inp",
}
# Primeiro ano que o exportador oferece; não é um corte do histórico.
ANO_INICIAL_EXPORTADOR = 1969

# Estruturas da cesta 2024 que contêm as séries do catálogo, por (tipo, frequencia).
ESTRUTURAS_CATALOGO = {
    ("indice", "mensal"): "112001700010",
    ("indice", "quinzenal"): "112001600020",
    ("incidencia", "mensal"): "112001800030",
    ("incidencia", "quinzenal"): "112001800020",
}

# Árvores por objeto do gasto (292 genéricos e seus agregados), por frequência.
ARVORES_GENERICOS = {
    "mensal": {"estrutura": "112001700030", "no_raiz": "1120017000300010"},
    "quinzenal": {"estrutura": "112001600030", "no_raiz": "1120016000300010"},
}

# Tamanho esperado das árvores; uma varredura incompleta é repetida e, se persistir, a ingestão para.
NUMERO_GENERICOS_ESPERADO = 292
NUMERO_NOS_COM_SERIE_ESPERADO = 463
TENTATIVAS_VARREDURA_ARVORE = 2

# Tabulados oficiais (gabarito da validação): serviço wsDataService do INEGI.
URL_TABULADO_INPC = "https://www.inegi.org.mx/app/tabulados/inp2/serviciocuadros/wsDataService.svc/obtienetabuladoinp/{cuadro}/{esquema}/1"
TABULADOS_OFICIAIS = {"mensal": "CA55_2018A", "quinzenal": "CA56_2018A"}
ESQUEMAS_TABULADO = {"atual": 4, "anterior": 1}  # 4 = período atual, 1 = período anterior

# Ponderadores e classificação dos genéricos por subíndice.
URLS_PONDERADORES = {
    "ponderadores_2024.xlsx": "https://www.inegi.org.mx/contenidos/programas/inpc/2018a/doc/Ponderadores_INPC%202024_Nacional_Final.xlsx",
    "ponderadores_2018.xlsx": "https://www.inegi.org.mx/contenidos/programas/inpc/2018/doc/PonderadoresINPC_Nacional.xlsx",
}

# ---------------------------------------------------------------------------
# Rede
# ---------------------------------------------------------------------------
CABECALHOS_HTTP = {"User-Agent": "Mozilla/5.0"}
TEMPO_LIMITE_SEGUNDOS = 60
NUMERO_TENTATIVAS = 5
ESPERAS_ENTRE_TENTATIVAS_SEGUNDOS = (2, 4, 8, 16, 32)
PAUSA_ENTRE_CHAMADAS_SEGUNDOS = 0.5
# Limite observado em 25/09/2026: 20 ids (com 21 o BIE devolve página de erro com HTTP 200).
# Histórico completo leva ~3 s por série; 10 ids (~25 s) ficam folgados no tempo limite de 60 s.
MAXIMO_IDS_POR_CHAMADA_BIE = 10
MAXIMO_IDS_POR_EXPORTACAO = 120  # lote de 120 genéricos leva ~13 s, abaixo do tempo limite

# ---------------------------------------------------------------------------
# Modo atualização
# ---------------------------------------------------------------------------
JANELA_SOBREPOSICAO_ANOS = 2  # ano atual e anterior
TOLERANCIA_REVISAO = 1e-9  # diferença mínima para registrar um valor como revisado

# ---------------------------------------------------------------------------
# Tratamento
# ---------------------------------------------------------------------------
ARQUIVO_SERIES = PASTA_PROCESSED / "series.parquet"
ARQUIVO_GENERICOS = PASTA_PROCESSED / "genericos.parquet"
ARQUIVO_PONDERADORES = PASTA_PROCESSED / "ponderadores.parquet"
ARQUIVO_HIERARQUIA = PASTA_PROCESSED / "hierarquia.parquet"

# O BIE entrega texto com ruído de ponto flutuante; arredonda-se à precisão publicada.
CASAS_DECIMAIS_BIE = {"indice": 3, "incidencia": 4}
MARCADORES_AUSENTES_EXPORTADOR = ("N/E", "NA")
DIA_INICIO_QUINZENA = {1: 1, 2: 16}
NIVEL_GENERICO = 4  # genéricos ficam abaixo dos subíndices (nível 3) na hierarquia

ABA_PONDERADORES = "CCIF"
CESTAS = {
    "2018": {"arquivo": "ponderadores_2018.xlsx", "vigencia_inicio": "2018-07-Q2", "vigencia_fim": "2024-07-Q1"},
    "2024": {"arquivo": "ponderadores_2024.xlsx", "vigencia_inicio": "2024-07-Q2", "vigencia_fim": None},
}
CESTA_VIGENTE = "2024"

# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------
ARQUIVO_RELATORIO_VALIDACAO = PASTA_PROCESSED / "relatorio_validacao.json"
# Ausências oficiais: o INEGI não publica a incidência de ago/2018 (nota do tabulado CA55:
# "El cálculo de la incidencia del mes de agosto del 2018 se ve afectada", mudança de base).
AUSENCIAS_OFICIAIS = {("incidencia", "mensal"): ["2018-08"]}
TOLERANCIA_DOIS_CANAIS_INDICE = 0.001
TOLERANCIA_DOIS_CANAIS_INCIDENCIA = 0.0001
TOLERANCIA_AGREGACAO_TEMPORAL = 0.001
ANO_INICIO_AGREGACAO_TEMPORAL = 1988
# Medido em 25/09/2026: o INPC geral cumpre a regra desde 1988 (desvio máx. 0,0005); os demais 15
# componentes só a partir de mar/1995 (antes, as séries retropoladas desviam até 0,03 da média das quinzenas).
PERIODO_INICIO_AGREGACAO_TEMPORAL_COMPONENTES = "1995-03"
TOLERANCIA_ADITIVIDADE_PONTOS = 0.01
ANO_INICIO_ADITIVIDADE = 2002
# Períodos de troca de base/cesta em que as incidências publicadas não fecham com a variação:
# jan/2011 (entrada da base 2a quincena dez/2010; nível 3 desvia 0,0128 pp, único caso acima de 0,01 em 565 períodos).
PERIODOS_EXCLUIDOS_ADITIVIDADE = {"mensal": ["2011-01"]}
TOLERANCIA_GABARITO_PONTOS = 0.01
TOLERANCIA_SOMA_PONDERADORES = 0.001
SOMA_PONDERADORES_ESPERADA = 100
TOLERANCIA_REAGREGACAO_PERCENTUAL = 0.01
PERIODO_INICIO_REAGREGACAO = {"quinzenal": "2024-07-Q2", "mensal": "2024-08"}
PERIODOS_POR_ANO = {"mensal": 12, "quinzenal": 24}
