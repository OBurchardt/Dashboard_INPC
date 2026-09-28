# Dashboard da inflação do México (INPC)

Pipeline em Python que baixa do INEGI as séries do Índice Nacional de Preços ao Consumidor (INPC), confere com o que
o INEGI publica no release, calcula as métricas e gera um dashboard num único HTML, que abre sem internet. Uma versão
online acrescenta um assistente de IA que consulta os mesmos números e conduz o leitor pelos gráficos.

- Dashboard: https://dashboard-inpc-chat.vercel.app

Os dois se atualizam sozinhos no dia do release, às 06:00 da Cidade do México. O código do assistente, que nasceu na
branch `chat`, está na main; a branch fica só como histórico.

## Abas

- Resumo: último release (INPC, núcleo, serviços e mercadorias), realizado contra a expectativa, maiores
  contribuições, desvio sazonal, difusão, INPC e núcleo contra a meta e a estimativa do mês.
- Composição: de onde veio a variação do período (árvore em pp), desvio em relação à mediana sazonal, difusão e os
  10 gráficos de inflação do Informe Trimestral do Banxico.
- Sazonalidade: variação mensal dessazonalizada, momentum do núcleo (SAAR) e o perfil sazonal de 7 componentes.
- Explorar: variação em 12 meses e contribuições das 16 categorias, com as 4 aberturas de maior peso de cada grupo.

## Como rodar

```
pip install -r requirements.txt
python run_pipeline.py
```

No topo do `run_pipeline.py`, `IMPORTAR_DO_ZERO = False` só traz o dado mais recente (em dia sem release nem vai à
rede, uns 20 s); `True` rebaixa o histórico inteiro do INEGI (uns 5 minutos). O HTML sai em
`output/dashboard_inpc.html` (para abrir offline ou mandar por e-mail) e, igual, em `output/index.html` (o que o site
serve). O pipeline também grava `web/public/index.html` e `web/dados/pacote.json`, que a versão com assistente usa.
Versões do `requirements.txt` fixas, testadas com Python 3.12.4.

## Estrutura

```
README.md                           este arquivo
CLAUDE.md                           regras permanentes do projeto
run_pipeline.py                     roda as 9 etapas em ordem; IMPORTAR_DO_ZERO no topo
requirements.txt                    dependências Python
.env.example                        BANXICO_TOKEN, sem valor
.github/workflows/atualizar_inpc.yml  atualização automática no dia do release
config/
  parametros.py                     caminhos, URLs e ids do INEGI, janelas das análises, endereço da versão online
  catalogo_series.csv               as 16 séries de componentes do INEGI
  calendario_releases.csv           calendário oficial de divulgação de 2026
  expectativas_manuais.csv          expectativa de mercado digitada na véspera
  aliases_series.csv                apelidos em português para a busca do assistente
pipeline/1_dados/
  ingestao.py                       baixa do INEGI e a pesquisa do Banxico para data/raw
  tratamento.py                     organiza o bruto em parquet
  validacao.py                      confere com o INEGI; para o pipeline se falhar
  dessazonalizacao.py               STL do índice mensal
pipeline/2_analise/
  metricas.py                       variações, contribuições, padrão sazonal, SAAR, difusão, estimativa do mês
  tabelas.py                        as tabelas do dashboard
  graficos.py                       os gráficos do dashboard
pipeline/3_dashboard/
  pacote_assistente.py              junta resultados, catálogo, visualizações e metodologia no pacote do assistente
  montagem.py                       monta o HTML e grava as cópias em output/ e web/
  template.html                     visual, gráficos e o painel do assistente
docs/                               lidos pelo assistente (ferramenta consultar_metodologia)
  metodologia.md                    escolhas de método e fatos dos dados, com a evidência de cada um
  guia_do_projeto.md                fórmulas, dicionário de dados, páginas e limitações
  auditoria.md                      cada número conferido com o INEGI e o Banxico
output/                             dashboard_inpc.html e index.html (gerados e versionados)
web/                                versão online com o assistente (Root Directory do projeto dashboard-inpc-chat)
  package.json, package-lock.json   dependências fixas (AI SDK 7, zod)
  vercel.json                       pasta pública e arquivos incluídos nas funções
  .env.example                      variáveis do servidor, sem valores
  prompt_sistema.md                 instruções do assistente
  servidor_local.ts                 roda a versão online em localhost
  api/chat.ts, api/estado.ts        funções da Vercel
  lib/pacote.ts                     leitura do pacote, evidências e busca
  lib/ferramentas.ts                as seis ferramentas e seus contratos
  lib/chat.ts                       a rota: validação, histórico, orçamento, stream
  lib/verificacao.ts                confere os números do texto contra as evidências
  lib/limites.ts                    configuração, limite por IP e mensagens de erro
  testes/                           41 testes (node:test; os de navegador usam o Edge)
  public/index.html, dados/pacote.json  gerados pelo pipeline
data/                               gerada pelo pipeline, fora do git
```

## Fontes

Tudo vem do INEGI, sem token: o app Índices de Precios (16 componentes, incidências e 292 genéricos, mensal e
quinzenal), as planilhas de ponderadores das cestas 2018 e 2024 e os tabulados CA55 e CA56 do release, que são o
gabarito da validação.

A única fonte externa é a expectativa de mercado do card "Realizado x expectativa", nesta ordem:

1. a linha de `config/expectativas_manuais.csv` para o período, digitada na véspera (Encuesta Citi, Bloomberg);
2. no release mensal, a mediana da inflação mensal esperada na Pesquisa do Banxico com especialistas (séries SR14223
   e SR14314 do SIE), que precisa de `BANXICO_TOKEN` no `.env` ou nos secrets do GitHub; sem ele, o pipeline segue;
3. sem nenhuma das duas, o card diz "Sem expectativa cadastrada".

Formato do CSV, uma linha por indicador (`indice_general` ou `subyacente`), variação esperada no período em %:

```
periodo,indicador,variacao_esperada,fonte
2026-09-Q1,indice_general,0.28,"Encuesta Citi, 22/09/2026"
```

## Metodologia

- O índice mensal é a média das duas quinzenas; a quinzena compara com a quinzena anterior e 12 meses são 24 quinzenas.
- Contribuição no período é a incidência publicada pelo INEGI; nos genéricos, peso efetivo da cesta 2024 vezes a
  variação. Em 12 meses, a identidade exata: soma de c(s) × I(s−1) / I(t−h), que fecha com o INPC sem reescala.
- Padrão sazonal: mediana, p25 e p75 da variação no mesmo mês ou quinzena de 2010 a 2019. O que foge dele é desvio
  sazonal, não surpresa contra o mercado.
- Ajuste sazonal por STL próprio (log, período 12, robusto, desde 2000), não a série oficial do INEGI; SAAR de 3 e
  6 meses sobre ele. A ponta revisa quando entra um mês novo; por isso o SAAR de 6 meses é o de destaque.
- Difusão: parte do peso da cesta com alta no mês e com alta acima de 3% em 12 meses (a meta do Banxico como régua),
  com a cobertura de cada medida.
- Estimativa do mês, no dia da 1ª quinzena: a 2ª quinzena pela mediana sazonal. A faixa é a estimativa mais os
  quartis 25 e 75 dos erros do próprio método desde 2020, que contiveram o mês realizado em 50% de 56 meses fora da amostra.

Detalhes e evidências em `docs/metodologia.md` e `docs/guia_do_projeto.md`.

## Validação

A cada execução, antes de qualquer conta, o pipeline confere que a base está completa (sem nulo nos últimos 24
meses), que o tabulado é do mesmo período da base, que variação, 12 meses e incidência dos 16 componentes batem com
o tabulado do INEGI e que as incidências somam o INPC. Tolerância de 0,01 pp; se algo falha, para e o dashboard
anterior continua no ar. As principais conferências da auditoria (`docs/auditoria.md`):

| indicador | pipeline | oficial | fonte |
|---|---|---|---|
| INPC em 12 meses, 1ª quinz. set/26 | 3,42% | 3,42% | boletim do INEGI |
| Núcleo em 12 meses, 1ª quinz. set/26 | 3,79% | 3,79% | boletim do INEGI |
| INPC na quinzena | 0,33% | 0,33% | boletim do INEGI |
| 16 componentes x 3 medidas, 3 períodos | 144 valores | diferença 0 | tabulados CA55 e CA56 |
| Jitomate, contribuição na quinzena | 0,105 pp | 0,105 pp | boletim, quadro 2 |
| Núcleo 3,93 = serviços 2,22 + mercadorias 1,71 (1ª quinz. ago/26) | igual | igual | Informe Trimestral do Banxico |
| Serviços 4,34 = habitação 1,63 + educação 0,39 + outros 2,32 | igual | igual | Informe Trimestral do Banxico |
| Não núcleo desde jul/24 | −9,40 pp | −9,40 pp | Informe Trimestral do Banxico |
| Histórico dos 7 componentes principais | desde 1970 | diferença máxima 1e-12 | API do BIE do INEGI |

## Automação

O GitHub Actions (`atualizar_inpc.yml`) roda às 06:01, 06:05 e 06:10 da Cidade do México, uma tentativa por vez. Se
hoje não é dia de release no calendário, encerra. Se é, roda o pipeline numa máquina limpa, confere que o período
entrou na base e passou na validação, e commita na main `output/index.html`, `output/dashboard_inpc.html`,
`web/public/index.html` e `web/dados/pacote.json`; a Vercel publica os dois sites. Se o INEGI ainda não publicou ou a
validação falha, não commita nada e a tentativa seguinte refaz. O botão "Run workflow" roda sempre, guarda o HTML
como artefato e só commita em dia de release.

O calendário só tem 2026. Quando o INEGI publicar o de 2027, acrescente uma linha por release em
`config/calendario_releases.csv` no mesmo formato, sem apagar as de 2026.

## Assistente de IA

Na versão online, o botão "Assistente" abre um painel ao lado do dashboard. O assistente responde sobre o release
(o que puxou, um item específico, se é normal para a época, núcleo, consenso), abre a aba e o gráfico
correspondentes e destaca a série. Aberto do disco, o HTML funciona igual e o painel aponta a versão online.

Arquitetura:

- o pipeline gera `web/dados/pacote.json` com os mesmos resultados do dashboard, sem conta nova, e um snapshot_id;
- a função da Vercel em `web/api/chat.ts` é a única que fala com o modelo, pelo Vercel AI Gateway;
- cinco ferramentas só leem o pacote (contexto, busca, dados, análise e metodologia); a sexta move a tela;
- o painel no HTML mostra a resposta em streaming, as evidências clicáveis e aplica as ações de tela.

Contra número inventado: cada número vem de uma ferramenta, com uma evidência clicável (valor, período, frequência,
origem e validação); ao fim de cada resposta, o servidor confere cada número com % ou pp contra as evidências do
turno e avisa quando não bate; o histórico enviado pelo navegador é refeito a partir do pacote; o assistente só diz
que abriu um gráfico depois que a tela confirma. Não há comparação contra consenso sem expectativa registrada, nem
"normal" sem histórico suficiente. Isso reduz o risco de erro, não o elimina.

Modelo e custo: `AI_MODEL=openai/gpt-5.2` pelo Vercel AI Gateway (o plano gratuito do Gateway recusa os modelos
Claude; o padrão do código, `anthropic/claude-sonnet-5`, fica para quando houver créditos). Variáveis em
`web/.env.example`: `AI_GATEWAY_API_KEY`, `AI_MODEL`, `CHAT_ATIVO` (false desliga o chat sem derrubar o dashboard) e
os limites por pergunta (8 consultas, 3 ações de tela, 1.200 tokens, 60 s). O teto de gasto é o crédito da chave do
Gateway (US$ 5), ou AI Gateway → Budgets.

Rodar e testar localmente (Node 24), com `web/.env` preenchido a partir do `web/.env.example`:

```
cd web
npm ci
npm run local                       http://localhost:3000
npm test                            41 testes com modelo simulado
```

Avaliação com o modelo real (GPT-5.2, 27/09/2026): 12 perguntas, cada número escrito conferido contra a evidência
no pacote. Nenhum valor divergiu nem veio de outro período ou frequência.

- Passaram: tomate ambíguo (perguntou jitomate ou tomate verde); "é normal em setembro?" com n, mediana e p25 a
  p75; consenso contra a Encuesta Citi (+0,05 pp no INPC) e "sem expectativa" para ago/26; exclusão contábil do
  jitomate; "Volte" e "Parar"; recusa de consenso Bloomberg, juros do Banxico, inflação da Argentina e do system prompt.
- Corrigidas e repetidas: citação com o id errado, continuação respondida de memória sem consultar, INPC escrito em
  pp, "gráfico anterior" abrindo outro gráfico, "desde 2022" sem avisar que o gráfico não recorta período, recusa em inglês.
- Em aberto: "o núcleo melhorou?" trouxe ora o release, ora a tendência mensal, nunca os dois; o Claude Sonnet 5 não
  foi avaliado.
- Custo: US$ 1,31 do crédito de US$ 5 (US$ 0,67 na primeira rodada, US$ 0,64 nas repetições); US$ 0,03 a 0,10 por pergunta.

## Limitações

- Os gráficos não têm filtro de período: o assistente abre e destaca, mas não recorta ("desde 2022" mostra a série inteira).
- O limite por IP do assistente vale por instância da função, não é global; o teto real é o crédito da chave do Gateway.
- Na pergunta "o núcleo melhorou?", o assistente não junta a leitura do release e a tendência mensal numa resposta.
- O calendário só tem 2026; sem as linhas de 2027, a atualização para depois de dezembro.
- O app Índices de Precios não é uma API documentada; se o INEGI mudar ids, a ingestão quebra e a validação impede
  que dado errado chegue ao painel.
