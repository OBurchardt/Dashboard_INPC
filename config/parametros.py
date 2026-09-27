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
EXPECTATIVAS_MANUAIS = RAIZ / "config" / "expectativas_manuais.csv"  # a expectativa de mercado digitada na véspera do release
for pasta in (PASTA_RAW, PASTA_PROCESSED, PASTA_OUTPUT):
    pasta.mkdir(parents=True, exist_ok=True)

# ==== 2. Tempo ====
FUSO = "America/Mexico_City"  # o INEGI divulga às 06:00 de lá
MESES_JANELA_ATUALIZACAO = 6  # no dia a dia rebaixo só os últimos 6 meses; se a base atrasou mais que isso, baixo o histórico inteiro

# ==== 3. Rede ====
TENTATIVAS_REDE = 3  # o servidor do INEGI derruba conexão de vez em quando; na terceira quase sempre vai
TEMPO_LIMITE_SEGUNDOS = 120  # um lote de 120 genéricos com o histórico inteiro leva uns 15 s, então sobra folga
LOTE_EXPORTACAO_IDS = 120  # pedir os 463 ids de uma vez passava de um minuto e às vezes caía

# ==== 4. Fontes do INEGI ====
URL_EXPORTADOR = "https://www.inegi.org.mx/app/indicesdeprecios/Exportacion.aspx?INPtipoExporta=CSV"
URL_ARVORE = "https://www.inegi.org.mx/app/indicesdeprecios/servicios/ArbolAjaxInteraccion.asmx/ObtieneNodosV2"
URL_TABULADO = "https://www.inegi.org.mx/app/tabulados/inp2/serviciocuadros/wsDataService.svc/obtienetabuladoinp/{cuadro}/4/1"
URLS_PONDERADORES = {
    "ponderadores_2024.xlsx": "https://www.inegi.org.mx/contenidos/programas/inpc/2018a/doc/Ponderadores_INPC%202024_Nacional_Final.xlsx",
    "ponderadores_2018.xlsx": "https://www.inegi.org.mx/contenidos/programas/inpc/2018/doc/PonderadoresINPC_Nacional.xlsx",
}

# ==== 5. Expectativas do Banxico (a única fonte fora do INEGI) ====
# Encuesta sobre las Expectativas de los Especialistas en Economía del Sector Privado, no SIE: mediana da inflação
# mensal esperada para o mês da pesquisa ("mes en curso"). A pesquisa de agosto sai no 1º dia útil de setembro,
# antes do INPC de agosto, então ela é a expectativa daquele release mensal. O token vem de BANXICO_TOKEN
URL_BANXICO_SIE = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/{series}/datos"
SERIES_EXPECTATIVA_BANXICO = {"indice_general": "SR14223", "subyacente": "SR14314"}

# ==== 6. Estruturas do app indicesdeprecios (cesta 2024) ====
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

# ==== 7. Componentes e nomes na tela ====
PERIODOS_POR_ANO = {"mensal": 12, "quinzenal": 24}  # a variação anual compara com 12 meses ou 24 quinzenas antes
COMPONENTES_PRINCIPAIS = ("indice_general", "subyacente", "no_subyacente")
COMPONENTES_NIVEL_2 = ("mercancias", "servicios", "agropecuarios", "energeticos_y_tarifas")
# o leitor é brasileiro, então na tela os componentes aparecem em português
NOMES_EXIBICAO = {
    "indice_general": "INPC geral",
    "subyacente": "Núcleo",
    "no_subyacente": "Não núcleo",
    "mercancias": "Mercadorias",
    "servicios": "Serviços",
    "agropecuarios": "Agropecuários",
    "energeticos_y_tarifas": "Energia e tarifas",
    "alimentos_bebidas_y_tabaco": "Alimentos, bebidas e tabaco",
    "mercancias_no_alimenticias": "Mercadorias não alimentícias",
    "vivienda": "Habitação",
    "educacion_colegiaturas": "Educação",
    "otros_servicios": "Outros serviços",
    "frutas_y_verduras": "Frutas e verduras",
    "pecuarios": "Pecuários",
    "energeticos": "Energia",
    "tarifas_autorizadas_por_el_gobierno": "Tarifas do governo",
}

# ==== 8. Janelas das análises e tolerância da validação ====
ANO_INICIO_DESSAZONALIZACAO = 2000  # antes disso a inflação era alta e o padrão sazonal se perde no ruído
ANOS_NORMA_SAZONAL = (2010, 2019)  # uma década de inflação comportada, antes da pandemia
ANO_INICIO_GRAFICOS = 2019  # um ano antes da pandemia
MES_BASE_NAO_NUCLEO = "2024-07"  # pico recente do não núcleo (10,36% em 12 meses); o gráfico mostra o que explicou a queda desde então
ABERTURAS_POR_SUBINDICE = 4  # na aba Explorar; a paleta só tem 4 cores bem distintas, o resto vira "Demais"
# a cesta 2024 entrou na 2a quinzena de julho de 2024; aqui vai o primeiro período em que ele e o anterior já estão nela
INICIO_CESTA_2024 = {"quinzenal": "2024-07-Q2", "mensal": "2024-08"}
MESES_METRICAS_GENERICOS = 24  # quanto histórico de genéricos vai para o dashboard
MESES_VALIDACAO_ADITIVIDADE = 24  # janela em que confiro se as incidências somam o INPC
TOLERANCIA_VALIDACAO_PP = 0.01  # o INEGI publica com 2 casas, então 0,01 pp é a menor diferença que dá para ver
