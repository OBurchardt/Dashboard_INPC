# Assistente (versão online, branch `chat`)

Este documento só existe na branch `chat`. Ele descreve o chat com IA que acompanha o dashboard na versão online:
de onde vêm os números, o contrato de cada ferramenta, o que o chat consegue fazer na tela, os limites de custo, os
testes e o que ainda não foi verificado. A main e o site `dashboard-inpc.vercel.app` não têm nada disso.

A branch `chat` é um retrato do release da 1ª quinzena de setembro de 2026. A atualização automática
(`.github/workflows/atualizar_inpc.yml`) só roda na main; para trazer um release novo para cá, é preciso rodar o
pipeline nesta branch e commitar.

## 1. Mapa de integração

```
pipeline (Python, os mesmos resultados do dashboard)
  metricas.py ──► metricas_componentes / metricas_genericos / metricas_difusao (.parquet), metricas_resumo.json, validacao.json
  graficos.py + template.html ──► registro das visualizações (id, aba, título, séries, métricas, frequência)
  docs/*.md ──► trechos de metodologia com id estável
        ▼  pacote_assistente.py
  data/processed/pacote_assistente.json   (snapshot_id = hash do conteúdo)
        ▼  montagem.py
  output/index.html (com DADOS.assistente) · web/public/index.html (cópia) · web/dados/pacote.json (cópia)
        ▼
  servidor (web/lib, TypeScript)                       navegador (painel no template.html)
  consultar_contexto ─┐                                 controlar_dashboard ──► abre aba, rola, destaca
  buscar_series       │ filtram, ordenam e selecionam   (adaptador que só conhece o registro)
  consultar_dados     ├ o pacote; evidências com id  ◄──── resultado: applied / unsupported / stale_state /
  analisar_componentes│                                     cancelled / error, depois do plotly desenhar
  consultar_metodologia┘
        ▲
  AI Gateway (anthropic/claude-sonnet-5) ◄── só o servidor fala com ele
```

| pergunta | fonte no pipeline | ferramenta | visualização aberta |
|---|---|---|---|
| O que puxou a divulgação? | incidência do período (INEGI; genéricos pelo peso efetivo) | `analisar_componentes` decomposição e ranking por `incidencia_periodo` | `main_top_incidencias` ou `decomp_arvore` |
| E o tomate? | `metricas_genericos` | `buscar_series` (ambíguo: Jitomate g070 e Tomate verde g076), `consultar_dados` | `explorar_frutas_y_verduras_anual` (Jitomate é a abertura 1) ou a linha de `main_top_incidencias` |
| Isso é normal em setembro? | `norma_mediana`, `norma_p25`, `norma_p75`, `norma_n` (2010–2019) | `analisar_componentes` comparação sazonal | `main_vs_norma` (componentes) ou `decomp_desvios` |
| Serviços contra mercadorias desde 2022 | `variacao_anual` | `consultar_dados` com `inicio` | `grupos_nucleo_anual` (sem filtro de período: o chat diz isso) |
| Veio acima do consenso? | `config/expectativas_manuais.csv` e Pesquisa do Banxico | `consultar_metodologia` tema `expectativas` | nenhuma (o card "Realizado x expectativa" não é visualização registrada) |

## 2. O que mudou no pipeline (só nesta branch)

- `metricas.py` passou a guardar o que já calculava e descartava: `norma_p25` e `norma_p75` dos genéricos, e
  `norma_n` (quantos anos de 2010–2019 entraram no padrão sazonal) nos componentes e nos genéricos. A contagem é a
  única conta nova, e não muda nenhum número do dashboard: `graficos.json`, `tabelas.json`, `metricas_resumo.json`
  e todas as colunas antigas saíram idênticas (conferido comparando com a cópia de antes da mudança).
- `pacote_assistente.py` é a etapa nova, entre `graficos.py` e `montagem.py`. Não calcula nada: seleciona e organiza.
- `montagem.py` põe em `DADOS.assistente` o snapshot, o release, o endereço da versão online e o registro das
  visualizações, e grava as cópias em `web/`. O resto do DADOS é o mesmo da main.
- `template.html` ganhou o botão "Assistente", o painel (seção 8 do CSS e do JavaScript) e nada mais.
- `config/parametros.py` ganhou a seção 9; `config/aliases_series.csv` tem os apelidos em português da busca.

## 3. Pacote de dados

`web/dados/pacote.json` (4,8 MB): `snapshot_id`, `gerado_em`, `release`, `validacao`, `metricas` (nome, unidade,
natureza observado/derivado/estimado, fonte, validação e tema da metodologia de cada métrica, com a variante dos
genéricos), `series` (337: 16 componentes, 292 genéricos, 28 itens que saíram da cesta 2018, sem série, e a
difusão), `valores` (componentes desde 2000; genéricos nos últimos 24 meses; 6 casas, ausente é `null`),
`expectativas`, `estimativa_do_mes`, `destaques`, `parametros`, `visualizacoes` (59) e `metodologia` (170 trechos de
`metodologia.md`, `guia_do_projeto.md` e `auditoria.md`, 17 temas, versão = hash dos três arquivos).

O `snapshot_id` é o hash do conteúdo sem a hora de geração nem a hora da validação: o mesmo dado dá o mesmo id em
qualquer rodada. O painel manda o snapshot com que foi montado; se o servidor tiver outro, responde 409 e nada é
analisado.

Validação com escopo, por métrica: `validado_no_release` só para variação, 12 meses e incidência dos 16 componentes
no último período (tabulados CA55/CA56) e para a aditividade das incidências; `conferido_na_auditoria` para o resto,
com o escopo da `docs/auditoria.md`; nos genéricos, a incidência é marcada como derivada (peso efetivo do projeto) e
conferida na auditoria, nunca como validada no release; expectativas são `fonte_externa_sem_conferencia`. Se o
release mudar, "conferido na auditoria" vira "método conferido na auditoria".

## 4. As seis ferramentas

Todas as entradas são objetos estritos (propriedade extra é erro), com enums e limites. Nenhuma aceita código,
SQL, seletor CSS, URL ou fórmula. Toda saída de dados usa o envelope
`{ status, snapshot_id, dados, evidencias, limitacoes }`, e cada evidência tem id estável `E-xxxxxx`, valor, unidade,
período, frequência, natureza, origem, validação e a visualização onde o número aparece.

| ferramenta | onde roda | entrada | fase |
|---|---|---|---|
| `consultar_contexto` | servidor | `{}` | 1, feita |
| `buscar_series` | servidor | `termo` (1–60), `tipo` (componente, generico, indicador, todos), `limite` (1–10) | 1, feita |
| `consultar_dados` | servidor | `series` (1–6 ids), `metricas` (1–6, enum), `frequencia`, `inicio`/`fim` ou `ultimos` (1–48), `snapshot_id` opcional | 1, feita |
| `analisar_componentes` | servidor | união por `operacao`: `ranking`, `decomposicao`, `comparacao_temporal`, `comparacao_sazonal`; na fase 2, `tendencia` e `exclusao_contabil` | 1, feita; as duas da fase 2 também, só no servidor |
| `consultar_metodologia` | servidor | `tema` (17, enum), `termo` opcional | 1, feita |
| `controlar_dashboard` | navegador | união por `acao`: `mostrar` (`visualizacao` do registro, `aba`, `destacar_serie`), `desfazer`, `restaurar_inicial` | 1, feita; filtros e janela ficam para a fase 2 |

Status possíveis: `ok`, `parcial`, `ambiguo`, `baixa_confianca`, `indisponivel`, `amostra_insuficiente`,
`erro_parametro`, `snapshot_divergente`, `orcamento_esgotado`; dentro de `consultar_dados`, por série e métrica,
`id_inexistente`, `metrica_indisponivel` e `fora_da_cobertura`. Nada ausente vira zero.

Regras que ficam no código, não no modelo:

- busca: exata (nome oficial, nome na tela, apelido ou id) ou aproximada (palavra inteira ou começo do nome), sem
  palpite por semelhança de letras; duas exatas é `ambiguo` e a ferramenta manda perguntar;
- ranking: o critério é explícito e o outro vem ao lado (quem ordena por variação vê a incidência, e vice-versa);
- decomposição: só filhos diretos, ou só genéricos (folhas), nunca o pai junto; total, soma, resíduo e itens sem dado.
  É a única conta do servidor, soma e subtração de valores exportados;
- comparação temporal: a mudança da taxa em pp é a diferença entre duas taxas exportadas (a mesma conta do cartão do
  dashboard) e vem separada da variação do índice no período;
- comparação sazonal: a mesma quinzena ou o mesmo mês de 2010–2019, com n, mediana, p25 e p75 do pipeline; período
  dentro de 2010–2019 é recusado (o ponto não pode estar na própria referência); com menos de 8 anos, `amostra_insuficiente`;
- realizado contra esperado: só com a expectativa registrada, e a diferença usa os dois números arredondados, como o card;
- tendência (fase 2): 12 meses, SAAR de 3 e 6 meses, variação dessazonalizada e difusão, lado a lado, sem nota nem
  índice composto, com o aviso de que o STL é do projeto e a ponta revisa;
- exclusão contábil (fase 2): variação do INPC no período menos as incidências retiradas, com a hipótese escrita;
  recusa item junto com um ancestral dele (dupla contagem) e diz que não é índice reponderado nem previsão; na
  quinzena, avisa que a conta em 12 meses exigiria encadear período a período, o que ela não faz.

`controlar_dashboard`: o schema só aceita visualização registrada e destaque de uma série que aparece nela. O
navegador confere o snapshot e a revisão do estado da tela capturada quando a pergunta saiu; se o usuário trocou de
aba no meio, a ação volta `stale_state` e não é aplicada. `applied` só sai depois de o plotly terminar de desenhar
(no Explorar, os gráficos acima do alvo são desenhados antes, para a rolagem parar no lugar certo). Confirmação de
tela não valida número.

## 5. Registro das visualizações

59 entradas geradas do `template.html` e do `graficos.json`, com id, abas, título, tipo, séries, métricas,
frequência, unidade, janela, destaques suportados e `filtros_suportados` (sempre vazio: as figuras não têm filtro).

| id | abas | título | tipo | métricas | frequência | destaque |
|---|---|---|---|---|---|---|
| main_inpc_meta | resumo | INPC geral vs meta | gráfico | variacao_anual | mensal com a última quinzena | — |
| main_core_meta | resumo | Núcleo vs meta | gráfico | variacao_anual | mensal com a última quinzena | — |
| main_vs_norma | resumo | Último período vs padrão sazonal | gráfico | variação, mediana, p25, p75 | do release | série |
| main_ultimos_periodos | resumo | Último release | tabela | variação, mediana, 12 meses | do release | linha |
| main_top_incidencias | resumo | Contribuições por abertura | tabela | variação, incidência | do release | linha |
| grupos_*_anual (5) | resumo e composição | INPC, núcleo, mercadorias, serviços, não núcleo | gráfico | variacao_anual | mensal com a última quinzena | série |
| grupos_*_contrib (4) | resumo e composição | contribuições para INPC, núcleo, mercadorias, serviços | gráfico | contribuicao_no_pai | mensal com a última quinzena | série |
| grupos_nao_nucleo_desde_base | composição | Não núcleo desde o mês-base | gráfico | contribuicao_no_grupo | mensal com a última quinzena | série |
| decomp_arvore | composição | Decomposição da variação do período | gráfico | incidência | do release | — |
| decomp_desvios | composição | Desvio em relação à mediana sazonal | tabela | variação, mediana, desvio ponderado | do release | linha |
| tend_difusao | composição | Difusão | gráfico | % da cesta em alta e acima de 3% | mensal | — |
| tend_dessazonalizado | sazonalidade | Variação mensal dessazonalizada | gráfico | variacao_sa_mensal | mensal | série |
| tend_momentum | sazonalidade | Momentum do núcleo | gráfico | SAAR 6m, 3m, 12 meses | mensal | — |
| tend_perfil_sazonal e sazon_perfil_* (7) | sazonalidade | perfis sazonais | gráfico | variação e padrão | mensal | — |
| explorar_*_anual e explorar_*_contrib (32) | explorar | as 16 categorias | gráfico | variacao_anual, contribuicao_no_pai | mensal com a última quinzena | série |

## 6. Servidor, protocolo e limites

- `/api/chat` (POST) e `/api/estado` (GET) em `web/api`, com a lógica em `web/lib`. O navegador não fala com o
  Gateway; a chave fica só no servidor. Sem CORS: pedido com `Origin` diferente, inclusive `null` (arquivo aberto do
  disco), é recusado.
- Protocolo: o stream de mensagens da UI do AI SDK 7 (SSE, `x-vercel-ai-ui-message-stream: v1`). Texto
  (`text-*`), andamento real (`tool-input-start` de cada ferramenta), evidência (dentro de `tool-output-available`),
  pedido de ação (`tool-input-available` de `controlar_dashboard`), resultado da ação (volta na continuação, como
  saída da ferramenta), erro (`error`) e fim (`finish`), mais `data-verificacao` no fim do turno.
- Verificação: cada número com % ou pp no texto precisa bater, na precisão escrita, com uma evidência do turno; id
  citado tem de existir; texto que diz ter aberto algo sem `applied` é marcado. O painel mostra "Números conferidos"
  ou um alerta. Isso reduz o risco de número inventado; não o elimina.
- Histórico: o navegador manda a conversa, mas o servidor refaz a partir do pacote todo resultado de ferramenta de
  dados que vier nela; da ação de tela só aceita o contrato do resultado, sem número. O system prompt é só o do
  servidor (`web/prompt_sistema.md`, o texto do Anexo B do Prompt 31).
- Orçamento por turno lógico (a pergunta mais as continuações depois de cada cena): 8 chamadas de dados e 3 cenas;
  acabou, a ferramenta devolve `orcamento_esgotado` e sai da lista oferecida ao modelo. Até 10 passos de modelo por
  pedido, 1.200 tokens de saída, 60 s. Tudo configurável por variável de ambiente.
- Custo: o limite por IP em memória (30 pedidos em 10 minutos) vale por instância da função, não é global. O teto
  global é o orçamento do AI Gateway (README, "Versão online"); o limite global por IP é uma regra de rate limit do
  Firewall da Vercel em `/api/chat`. `CHAT_ATIVO=false` desliga o chat e o dashboard continua no ar.
- Cache por snapshot + ferramenta + argumentos. A conversa não é guardada em lugar nenhum; o log tem só metadados
  (snapshot, passos, chamadas, cenas, duração, tipo e status de erro).

## 7. Testes

`cd web && npm test` roda 40 testes com `node:test`. Todos usam um modelo simulado por roteiro: provam o protocolo,
as proteções e as contas, não a qualidade do modelo real.

| arquivo | o que cobre |
|---|---|
| `ferramentas.test.ts` (16) | snapshot; tomate ambíguo entre Jitomate e Tomate verde; núcleo, core e serviços; termo sem correspondência; ranking por incidência igual ao quadro 2 do boletim e diferente do ranking por variação; unidades, sinais e frequência; quinzenal, mensal e 12 meses; padrão sazonal da mesma quinzena com n e faixa (INPC 0,32%, p25 0,23%, p75 0,34%); amostra insuficiente e ponto dentro da referência; decomposição do Informe do Banxico (serviços 4,34 = 2,32 + 1,63 + 0,39) sem dupla contagem; dado ausente, métrica inexistente e expectativa inexistente; snapshot divergente, parâmetro inválido, id inexistente e alvo de tela inválido; evidências rastreáveis; estimativa do mês marcada como estimativa; fase 2: tendência (SAAR 6m do núcleo 3,90% em ago/26) e exclusão contábil (0,33% − 0,105 pp = 0,22%, sem dupla contagem) |
| `rota.test.ts` (14) | stream com andamento, evidência e verificação; número sem evidência e citação inventada; histórico adulterado pelo navegador; orçamento de 8 consultas; "Acompanhar no dashboard" desligado; cena que para o stream e continuação; ação que falhou e texto que diz ter aberto; alvo de tela inexistente; instrução maliciosa como conteúdo; system prompt do cliente recusado; snapshot divergente; erro do Gateway sem vazar detalhe; falta de chave, chat desligado, limite por IP, origem de fora e pedido inválido; cancelamento |
| `sse.test.ts` (2) | o leitor de SSE do painel, tirado do template: eventos partidos em pedaços de 7 bytes e acentos partidos no meio; `[DONE]` e cancelamento |
| `navegador.test.ts` (8) | no Edge: HTML aberto do disco sem chamar servidor; backend fora do ar; fluxo do jitomate (consulta, abre o bloco de Frutas e verduras no Explorar, card centralizado, só o Jitomate opaco, evidência clicável, painel sem cobrir o gráfico); troca manual de aba durante a resposta (`stale_state`); parar; teclado, foco e plotly redimensionado; texto do modelo sem HTML nem link; tela de 390 px |

As referências numéricas dos testes são números publicados (boletim do INEGI e Informe do Banxico) que a
`docs/auditoria.md` já conferiu contra o pipeline; nenhuma é recalculada com a lógica testada.

**Avaliação com o modelo real: não feita.** Esta máquina não tem `AI_GATEWAY_API_KEY`, e o projeto novo na Vercel
não foi criado. Precisão numérica, coerência econômica e navegação com o Claude Sonnet 5 de verdade continuam sem
avaliação; o roteiro está na seção 9.

## 8. Limitações conhecidas

- Da fase 2, só a tendência e a exclusão contábil foram feitas. Ficaram de fora: filtro e janela temporal nos
  gráficos, várias cenas com "Continuar", reconexão do SSE e retomada do histórico. Hoje, "desde 2022" abre o
  gráfico inteiro e o chat deve dizer que não há filtro de período.
- A conversa some ao recarregar a página (nada é guardado); por isso não há ação antiga a reexecutar.
- O limite por IP não é global (seção 6). O teto de gasto depende de configurar o orçamento no Gateway.
- A verificação confere número e unidade, não o sentido da frase: um número certo pode estar na frase errada.
- No destaque de série, as etiquetas de valor na ponta das séries apagadas continuam visíveis.
- O card "Realizado x expectativa" e a faixa do release não são visualizações registradas; o chat não os abre.
- Os genéricos têm só 24 meses no pacote; histórico sazonal dos genéricos vem só pelos quartis exportados.

## 9. Roteiro de avaliação com o modelo real

Com a chave configurada, fazer as perguntas abaixo, cada uma numa conversa nova, e registrar para cada uma: as
ferramentas chamadas e os argumentos, as ações de tela e o status, as evidências citadas, a conclusão e as falhas.
Julgar separado: precisão numérica (cada número bate com a evidência e com o dashboard), coerência econômica
(unidade, frequência, período equivalente, nada de causa sem evidência, estimativa como estimativa) e navegação
(abriu a visualização certa, só disse "abri" depois de applied, respeitou "Pare", "Volte" e "sem mexer na tela").

1. O que puxou a inflação nesta divulgação?
2. E o tomate?
3. Mas isso é normal em setembro?
4. Mostre serviços contra mercadorias desde 2022.
5. Veio acima do consenso? (e, em seguida, para ago/26, que não tem expectativa registrada)
6. A inflação subjacente melhorou ou foi só o não núcleo?
7. Quanto daria sem o tomate?
8. Abra o gráfico anterior · Pare · Volte · Só explique, sem mexer na tela.

## 10. Para o documento do case (Word)

> Texto para o candidato revisar. As partes entre colchetes dependem de passos que não foram feitos nesta sessão.

**Como a IA foi incorporada.** O dashboard continua sendo o produto: um HTML que abre sem internet, com números
conferidos com o INEGI e o Banxico. A IA entra numa versão online separada, como um assistente que consulta os
mesmos resultados do pipeline e conduz o leitor pelos gráficos que já existem. Ela não calcula métrica nova nem lê
números de gráfico: o pipeline exporta um pacote com os resultados já calculados, e o assistente só pode consultá-lo
por seis ferramentas com contratos fechados (buscar uma série, consultar valores, ranquear e decompor contribuições,
comparar com o padrão sazonal de 2010–2019, ler a metodologia e mover a tela).

**Como os números ficam conferíveis.** Cada número que o assistente escreve vem com uma evidência clicável que diz o
valor, o período, a frequência, a origem e como aquela métrica foi validada. Antes de marcar a resposta como
concluída, o servidor confere se cada número do texto bate com uma evidência daquele turno e avisa quando não bate.
Isso reduz, mas não elimina, o risco de erro; a leitura final continua sendo do economista.

**O que o assistente se recusa a fazer.** Chamar de "surpresa" o que é desvio do padrão sazonal; comparar contra
consenso quando não há expectativa registrada (hoje só a Encuesta Citi para setembro/26); classificar como normal um
item sem histórico suficiente; somar um grupo aos próprios subgrupos; atribuir causa a uma contribuição contábil.

**Navegação.** Quando explica um dado, o assistente abre a aba e o gráfico correspondentes e destaca a série; o
leitor vê a mesma evidência no dashboard. Só diz que abriu depois que a tela confirma, respeita mudanças manuais e
pode ser desligado ("Acompanhar no dashboard").

**Custos e segurança.** O modelo (Claude Sonnet 5, pelo AI Gateway da Vercel) só é chamado pelo servidor; a chave
nunca vai ao navegador. Cada pergunta tem orçamento de consultas e de tempo, e o chat pode ser desligado sem derrubar
o dashboard. [Orçamento de gasto configurado no Gateway: US$ ___ por ___ — a confirmar.]

**Validação.** [A confirmar pelo candidato: avaliação com o modelo real nas oito perguntas da seção 9, com os
resultados.] Os testes automáticos (40) usam um modelo simulado e cobrem protocolo, contas e navegação, não a
qualidade das respostas do modelo real.
