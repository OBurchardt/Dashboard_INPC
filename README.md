# Dashboard da inflação do México (INPC)

> **Branch `chat`.** Esta branch acrescenta ao dashboard um assistente com IA numa versão online separada. Ela é um
> retrato do release da 1ª quinzena de setembro de 2026: a atualização automática só roda na main. Tudo sobre o
> assistente está em `docs/assistente.md` e na seção "Versão online com assistente", no fim deste arquivo.

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
  aliases_series.csv                [branch chat] apelidos em português para a busca do assistente
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
    pacote_assistente.py            [branch chat] junta resultados, catálogo, registro de visualizações e metodologia no pacote do assistente
    montagem.py                     junta tabelas e gráficos no template
    template.html                   esqueleto HTML do dashboard
docs/
  metodologia.md                    registro das escolhas metodológicas e justificativas
  guia_do_projeto.md                como rodar, fluxo, fórmulas, dicionário de dados e páginas
  auditoria.md                      auditoria final: cada número conferido com o INEGI e o Banxico, e os bugs achados
  assistente.md                     [branch chat] pacote, contratos das ferramentas, registro de visualizações, limites, testes e texto para o Word
.github/workflows/
  atualizar_inpc.yml                no dia do release, roda o pipeline no GitHub e grava o HTML novo na main
data/                               [gerada pelo pipeline]
  raw/                              CSVs período x série, árvores de genéricos, ponderadores e tabulados
  processed/                        series, genericos, ponderadores, tabulado_oficial, metricas_* (.parquet), resumo, gráficos, tabelas e validação (.json)
output/                             [gerada pelo pipeline e versionada] dashboard_inpc.html e index.html, o mesmo HTML
web/                                [branch chat] a versão online com o assistente (Root Directory do segundo projeto na Vercel)
  package.json, package-lock.json   dependências fixas (AI SDK 7, zod) e os scripts local e test
  vercel.json                       pasta pública, duração e arquivos incluídos nas funções
  .env.example                      variáveis do servidor, sem valores
  prompt_sistema.md                 system prompt do assistente, versionado
  servidor_local.ts                 roda a versão online em localhost
  api/chat.ts, api/estado.ts        funções da Vercel
  lib/                              pacote.ts, ferramentas.ts, chat.ts, verificacao.ts, limites.ts
  testes/                           40 testes (node:test; os de navegador usam o Edge)
  public/index.html                 [gerada pela montagem] cópia do output/index.html
  dados/pacote.json                 [gerada pela montagem] cópia do pacote do assistente
```

## Fluxo

```
INEGI (indicesdeprecios, ponderadores, tabulados) → ingestao → data/raw → tratamento → data/processed → validacao → dessazonalizacao → metricas → tabelas + graficos → pacote_assistente → montagem → output/dashboard_inpc.html (e, na branch chat, web/)
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

## Versão online com assistente (branch `chat`)

O HTML desta branch tem um botão "Assistente". Aberto do disco, o painel diz que a análise com IA precisa de conexão
e aponta a versão online; o dashboard funciona igual. Na versão online, o painel conversa com `/api/chat`, que usa o
Vercel AI Gateway. O que o assistente faz, e o que não faz, está em `docs/assistente.md`.

Instalar e gerar os dados (Node 24 e o Python do projeto):

```
python run_pipeline.py              gera o pacote e grava web/public/index.html e web/dados/pacote.json
cd web
npm ci
```

Configurar: copie `web/.env.example` para `web/.env` e preencha `AI_GATEWAY_API_KEY` (a chave do AI Gateway, em
vercel.com → AI Gateway → API Keys). O `.env` nunca é versionado; a chave não aparece no código nem nos logs.

Rodar e testar:

```
npm run local                       versão online em http://localhost:3000 (sem chave, o painel diz que falta AI_GATEWAY_API_KEY)
npm test                            41 testes com modelo simulado; os de navegador usam o Microsoft Edge instalado
npm run tipos                       checagem de tipos
```

Publicar como projeto novo na Vercel (sem mexer no projeto `dashboard-inpc`, que continua servindo a main):

1. vercel.com → Add New → Project → Import do mesmo repositório `Dashboard_INPC`.
2. Project Name: `dashboard-inpc-assistente` (se usar outro, troque `URL_VERSAO_ONLINE` em `config/parametros.py`,
   rode o pipeline e commite).
3. Framework Preset: Other. Root Directory: `web`. Build Command: vazio. Install Command: `npm ci`. Output
   Directory: `public` (já está no `vercel.json`). Com a raiz em `web/`, o `requirements.txt` da raiz fica fora do
   projeto e a Vercel não procura funções Python.
4. Environment Variables: `AI_GATEWAY_API_KEY` (ou deixe vazia e use a autenticação OIDC do próprio projeto, que o
   Gateway aceita em deploys da Vercel), `AI_MODEL` e, se quiser, os limites do `.env.example`. No plano gratuito do
   Gateway os modelos Claude são recusados: use `AI_MODEL=openai/gpt-5.2`, o modelo avaliado em `docs/assistente.md`
   §9; com créditos pagos, `anthropic/claude-sonnet-5` (o padrão do código), repetindo a avaliação.
5. Deploy. Na importação a Vercel usa a branch padrão (main), que não tem `web/`: esse primeiro deploy falha, e é o
   esperado. Em Settings → Git, ponha a Production Branch em `chat` e dispare o deploy da `chat` (Deployments →
   Redeploy do último commit da branch, ou um push nela).
6. Teto de gasto: vercel.com → AI Gateway → Budgets (ou `vercel ai-gateway budgets set project dashboard-inpc-assistente
   --limit <US$> --refresh-period monthly`). Esse é o limite global; o limite por IP do código vale só por instância.
   Para limite global por IP, crie em Firewall uma regra de rate limit para `/api/chat`.
7. Para desligar o chat sem derrubar o dashboard: `CHAT_ATIVO=false` e redeploy.

