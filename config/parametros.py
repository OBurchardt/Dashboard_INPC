# Parâmetros do projeto: o que um humano pode querer ajustar sem mexer no código.
# Todas as etapas leem este arquivo. Ao ser importado, ele cria as pastas de dados.

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
FUSO = "America/Mexico_City"  # o INEGI divulga às 06:00 da Cidade do México
MESES_JANELA_ATUALIZACAO = 6  # a atualização rebaixa os últimos 6 meses; atraso maior refaz tudo

# ==== 3. Fontes do INEGI ====
URL_EXPORTADOR = "https://www.inegi.org.mx/app/indicesdeprecios/Exportacion.aspx?INPtipoExporta=CSV"
URL_ARVORE = "https://www.inegi.org.mx/app/indicesdeprecios/servicios/ArbolAjaxInteraccion.asmx/ObtieneNodosV2"
URL_TABULADO = "https://www.inegi.org.mx/app/tabulados/inp2/serviciocuadros/wsDataService.svc/obtienetabuladoinp/{cuadro}/4/1"
URLS_PONDERADORES = {
    "ponderadores_2024.xlsx": "https://www.inegi.org.mx/contenidos/programas/inpc/2018a/doc/Ponderadores_INPC%202024_Nacional_Final.xlsx",
    "ponderadores_2018.xlsx": "https://www.inegi.org.mx/contenidos/programas/inpc/2018/doc/PonderadoresINPC_Nacional.xlsx",
}

# ==== 4. Estruturas do app indicesdeprecios (cesta 2024) ====
# Onde estão os 16 componentes e as 16 incidências do catálogo, por (tipo, frequência).
ESTRUTURAS = {
    ("indice", "mensal"): "112001700010",
    ("indice", "quinzenal"): "112001600020",
    ("incidencia", "mensal"): "112001800030",
    ("incidencia", "quinzenal"): "112001800020",
}
# Árvore por objeto do gasto, que contém os 292 genéricos: (estrutura, nó raiz).
ARVORES = {
    "mensal": ("112001700030", "1120017000300010"),
    "quinzenal": ("112001600030", "1120016000300010"),
}
# Tabulados oficiais do último release, usados como gabarito na validação.
TABULADOS = {"mensal": "CA55_2018A", "quinzenal": "CA56_2018A"}
