# Tudo o que eu posso querer mudar sem abrir o código das etapas fica aqui: caminhos, endereços
# do INEGI, ids das estruturas do app, janelas das análises e os nomes que aparecem na tela.
# Todas as etapas importam este arquivo, e só ele. Importar já cria as pastas de dados, então
# uma máquina nova não precisa preparar nada antes de rodar.

from pathlib import Path

# ==== 1. Caminhos ====
RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = RAIZ / "data" / "raw"
PASTA_PROCESSED = RAIZ / "data" / "processed"
PASTA_OUTPUT = RAIZ / "output"
CATALOGO = RAIZ / "config" / "catalogo_series.csv"
CALENDARIO = RAIZ / "config" / "calendario_releases.csv"
for pasta in (PASTA_RAW, PASTA_PROCESSED, PASTA_OUTPUT):
    pasta.mkdir(parents=True, exist_ok=True)

# ==== 2. Tempo ====
FUSO = "America/Mexico_City"  # o INEGI divulga às 06:00 de lá, e é esse relógio que decide se já saiu dado
MESES_JANELA_ATUALIZACAO = 6  # no dia a dia rebaixo só os últimos 6 meses; atrasado mais que isso, refaço tudo

# ==== 3. Rede ====
TENTATIVAS_REDE = 3  # o servidor do INEGI derruba conexão de vez em quando; na terceira quase sempre vai
TEMPO_LIMITE_SEGUNDOS = 120  # um lote de 120 genéricos com o histórico inteiro leva uns 15 s, então sobra folga
LOTE_EXPORTACAO_IDS = 120  # pedir os 463 de uma vez passava de um minuto e às vezes caía

# ==== 4. Fontes do INEGI ====
URL_EXPORTADOR = "https://www.inegi.org.mx/app/indicesdeprecios/Exportacion.aspx?INPtipoExporta=CSV"
URL_ARVORE = "https://www.inegi.org.mx/app/indicesdeprecios/servicios/ArbolAjaxInteraccion.asmx/ObtieneNodosV2"
URL_TABULADO = "https://www.inegi.org.mx/app/tabulados/inp2/serviciocuadros/wsDataService.svc/obtienetabuladoinp/{cuadro}/4/1"
URLS_PONDERADORES = {
    "ponderadores_2024.xlsx": "https://www.inegi.org.mx/contenidos/programas/inpc/2018a/doc/Ponderadores_INPC%202024_Nacional_Final.xlsx",
    "ponderadores_2018.xlsx": "https://www.inegi.org.mx/contenidos/programas/inpc/2018/doc/PonderadoresINPC_Nacional.xlsx",
}

# ==== 5. Estruturas do app indicesdeprecios (cesta 2024) ====
# ids que achei navegando no app: onde moram os 16 componentes e as 16 incidências, por tipo e frequência
ESTRUTURAS = {
    ("indice", "mensal"): "112001700010",
    ("indice", "quinzenal"): "112001600020",
    ("incidencia", "mensal"): "112001800030",
    ("incidencia", "quinzenal"): "112001800020",
}
# a árvore por objeto do gasto é a única que desce até os 292 genéricos: (estrutura, nó raiz)
ARVORES = {
    "mensal": ("112001700030", "1120017000300010"),
    "quinzenal": ("112001600030", "1120016000300010"),
}
# o tabulado que o INEGI publica no release é o gabarito da validação
TABULADOS = {"mensal": "CA55_2018A", "quinzenal": "CA56_2018A"}

# ==== 6. Componentes e nomes de exibição ====
PERIODOS_POR_ANO = {"mensal": 12, "quinzenal": 24}  # para a variação anual: 12 meses atrás, ou 24 quinzenas
COMPONENTES_PRINCIPAIS = ("indice_general", "subyacente", "no_subyacente")
COMPONENTES_NIVEL_2 = ("mercancias", "servicios", "agropecuarios", "energeticos_y_tarifas")
# os nomes do INEGI não cabem em eixo nem em tabela; aqui ficam os que eu uso na tela
NOMES_EXIBICAO = {
    "indice_general": "INPC geral",
    "subyacente": "Subyacente",
    "no_subyacente": "No subyacente",
    "mercancias": "Mercancías",
    "servicios": "Servicios",
    "agropecuarios": "Agropecuarios",
    "energeticos_y_tarifas": "Energéticos e tarifas",
    "alimentos_bebidas_y_tabaco": "Alimentos, bebidas e tabaco",
    "mercancias_no_alimenticias": "Mercancías não alimentícias",
    "vivienda": "Vivienda",
    "educacion_colegiaturas": "Educação (colegiaturas)",
    "otros_servicios": "Outros serviços",
    "frutas_y_verduras": "Frutas e verduras",
    "pecuarios": "Pecuarios",
    "energeticos": "Energéticos",
    "tarifas_autorizadas_por_el_gobierno": "Tarifas do governo",
}

# ==== 7. Janelas das análises e tolerância da validação ====
ANO_INICIO_DESSAZONALIZACAO = 2000  # antes disso a inflação era alta e o padrão sazonal se perde no ruído
ANOS_NORMA_SAZONAL = (2010, 2019)  # uma década de inflação comportada, antes da pandemia bagunçar tudo
ANO_INICIO_GRAFICOS = 2019  # começo o histórico dos gráficos um ano antes da pandemia, para ter referência
# a cesta 2024 entrou na 2a quinzena de julho de 2024; o primeiro período em que ele e o anterior já estão nela
INICIO_CESTA_2024 = {"quinzenal": "2024-07-Q2", "mensal": "2024-08"}
MESES_METRICAS_GENERICOS = 24  # quanto histórico de genéricos vai para o dashboard
MESES_VALIDACAO_ADITIVIDADE = 24  # janela em que confiro se as incidências somam o INPC
TOLERANCIA_VALIDACAO_PP = 0.01  # o INEGI publica com 2 casas, então 0,01 pp é a menor diferença que dá para ver
