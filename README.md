# Dashboard da inflação do México (INPC)

Pipeline em Python que baixa do INEGI as séries do Índice Nacional de Preços ao Consumidor (INPC) do México, confere com os números que o INEGI publica no release, calcula as métricas e gera um dashboard num único HTML, que abre sem internet. É feito para ser aberto no momento do release, às 06:00 da Cidade do México, e se atualiza sozinho no GitHub nesses dias.

## Estrutura

```
README.md                           visão geral do projeto (este arquivo)
CLAUDE.md                           regras permanentes do projeto
run_pipeline.py                     orquestra as etapas na ordem; IMPORTAR_DO_ZERO no topo
requirements.txt                    dependências Python
.gitignore                          arquivos fora do controle de versão
.env.example                        a chave BANXICO_TOKEN, sem valor; copie para .env e preencha
config/
  parametros.py                     caminhos, fuso, URLs e ids do INEGI, janela de atualização
  catalogo_series.csv               lista das séries do INEGI a baixar
  calendario_releases.csv           calendário oficial de divulgação do INPC
  expectativas_manuais.csv          expectativa de mercado digitada na véspera do release
pipeline/
  1_dados/
    ingestao.py                     baixa do INEGI (app indicesdeprecios, ponderadores, tabulados) e a pesquisa do Banxico para data/raw/
    tratamento.py                   organiza o bruto em parquet (séries, genéricos, ponderadores, tabulado)
    validacao.py                    confere completude, tabulado em dia, último release e incidências; para o pipeline se falhar
    dessazonalizacao.py             gera séries dessazonalizadas e comparação sazonal
  2_analise/
    metricas.py                     variações, contribuições, mediana sazonal, SAAR, difusão e o resumo do release
    tabelas.py                      formata as tabelas do dashboard
    graficos.py                     desenha os gráficos do dashboard
  3_dashboard/
    montagem.py                     junta tabelas e gráficos no template
    template.html                   esqueleto HTML do dashboard
docs/
  metodologia.md                    registro das escolhas metodológicas e justificativas
  guia_do_projeto.md                como rodar, fluxo, fórmulas, dicionário de dados e páginas
  auditoria.md                      auditoria final: cada número conferido com o INEGI e o Banxico, e os bugs achados
.github/workflows/
  atualizar_inpc.yml                no dia do release, roda o pipeline no GitHub e grava o HTML novo na main
data/                               [gerada pelo pipeline]
  raw/                              CSVs período x série, árvores de genéricos, ponderadores e tabulados
  processed/                        series, genericos, ponderadores, tabulado_oficial, metricas_* (.parquet), resumo, gráficos, tabelas e validação (.json)
output/                             [gerada pelo pipeline e versionada] dashboard_inpc.html e index.html, o mesmo HTML
```

## Fluxo

```
INEGI (indicesdeprecios, ponderadores, tabulados) → ingestao → data/raw → tratamento → data/processed → validacao → dessazonalizacao → metricas → tabelas + graficos → montagem → output/dashboard_inpc.html
```

## Como rodar

Instale as dependências (`pip install -r requirements.txt`) e rode `python run_pipeline.py`.
No topo do `run_pipeline.py`, `IMPORTAR_DO_ZERO = False` só atualiza a base com o dado mais recente;
`True` rebaixa todo o histórico do INEGI como se a base não existisse.

## Expectativas

O projeto não tem acesso a Bloomberg nem a outras fontes pagas de consenso. Por isso o destaque "Realizado x
expectativa" usa duas fontes, nesta ordem, para o INPC geral e o núcleo:

1. a linha de `config/expectativas_manuais.csv` para o período do release, digitada à mão na véspera (por exemplo,
   a Encuesta Citi para a quinzena, ou o consenso Bloomberg quando houver);
2. no release mensal, sem linha manual, a mediana da inflação mensal esperada na Pesquisa do Banxico com os
   especialistas do setor privado (séries SR14223 e SR14314 do SIE), baixada pela ingestão;
3. sem nenhuma das duas, o card diz "Sem expectativa cadastrada para <período>".

O CSV tem quatro colunas: `periodo` no formato do projeto (`2026-09-Q1` para a 1ª quinzena, `2026-09` para o mês),
`indicador` (`indice_general` ou `subyacente`), `variacao_esperada` (variação no período, em %, com ponto decimal)
e `fonte` (o texto que aparece no card). Uma linha por indicador:

```
periodo,indicador,variacao_esperada,fonte
2026-09-Q1,indice_general,0.28,"Encuesta Citi, 22/09/2026"
2026-09-Q1,subyacente,0.19,"Encuesta Citi, 22/09/2026"
```

A Pesquisa do Banxico precisa de um token gratuito da API SIE
(https://www.banxico.org.mx/SieAPIRest/service/v1/token): localmente, no `.env` como `BANXICO_TOKEN` (veja o
`.env.example`); no GitHub, em Settings → Secrets and variables → Actions, com o mesmo nome. Sem token, ou com a
API fora do ar, o pipeline segue normalmente, só sem a expectativa do Banxico.

## Ver ao vivo

O site na Vercel serve o `output/index.html` da branch `main`. Cada commit na main que muda esse arquivo
publica a versão nova; o `dashboard_inpc.html` é o mesmo HTML, para abrir offline ou mandar por e-mail.

## Rodar no GitHub

O workflow "Atualizar dashboard do INPC" (`.github/workflows/atualizar_inpc.yml`) dispara sozinho todo dia às
06:01, 06:05 e 06:10 da Cidade do México, uma execução por vez. Se hoje não é dia de release no
`config/calendario_releases.csv`, ele encerra sem fazer nada. Se é, e nenhuma tentativa anterior já publicou o
release, ele roda `python run_pipeline.py` numa máquina limpa (a base começa vazia e a ingestão baixa o histórico
inteiro, uns 5 minutos), confere se o período do release entrou na base e, se entrou e a validação passou, commita
`output/index.html` e `output/dashboard_inpc.html` na main com a mensagem "Atualização automática: <período>",
e a Vercel publica. Se o INEGI ainda não publicou ou a validação falha, o job fica vermelho, não commita nada e a
tentativa seguinte refaz. Se as três falharem, use o botão "Run workflow" na aba Actions: o disparo manual roda
sempre e guarda o HTML como artefato, mas só commita em dia de release. O push usa o `GITHUB_TOKEN` do próprio
Actions; não há token novo.

## Calendário do ano seguinte

O `config/calendario_releases.csv` só tem os releases de 2026; depois do último, o dashboard avisa que falta o calendário.
Quando o INEGI publicar o calendário do ano seguinte, acrescente uma linha por release no mesmo formato
(data, 06:00, America/Mexico_City, tipo e mês de referência) e rode o pipeline normalmente.
