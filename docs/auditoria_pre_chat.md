# Auditoria antes do chat

Fiz esta auditoria antes de pôr um chat em cima do dashboard, porque um chat repete com confiança o que a base disser. Revisei oito pontos que podiam produzir número errado ou texto enganoso. Para cada um anoto o problema, a evidência, a correção e o antes e depois. Os números são do release da 1ª quinzena de setembro de 2026 (base até ago/26 no mensal e 2026-09-Q1 no quinzenal).

Não chamo nada aqui de "100% validado". A validação confere a base contra o que o INEGI publica e contra identidades contábeis; ela não garante que o INEGI não errou, nem que uma leitura econômica esteja certa.

Os testes e exercícios rodaram no terminal, sem arquivo salvo no projeto e sem mexer nos dados reais: os testes de falha alteram em memória o que a validação lê e gravam o `validacao.json` fora do projeto.

## Resumo

| # | ponto | o que estava errado | o que mudou |
|---|---|---|---|
| 1 | contribuição anual | soma simples das incidências reescalada para fechar | identidade exata, sem reescala, janela completa |
| 2 | difusão | um só conjunto de itens para todas as medidas, sem cobertura | conjunto válido por medida, itens e cobertura guardados e no tooltip |
| 3 | validação | NaN, componente ausente e tabulado atrasado passavam | quatro checagens, nenhum nulo passa, mensagem diz o que faltou |
| 4 | linguagem | "surpresa" sugeria expectativa de mercado | "desvio sazonal ponderado", com o aviso na tela |
| 5 | mensal implícito | nunca tinha sido testado | backtest sem informação futura; fica como estimativa, faixa com cobertura informada |
| 6 | SAAR | revisão de fim de amostra desconhecida | exercício pseudo-tempo-real; 6 meses em destaque |
| 7 | documentação do quinzenal | dizia que os métodos não aceitam 24 períodos | corrigido: o X-13 não aceita, o STL aceitaria |
| 8 | card vazio e workflow | card "Em construção" e workflow vazio | card e aba saíram; workflow manual que publica o HTML como artefato |

## 1. Contribuição anual

**Problema.** A contribuição de cada componente para a inflação em 12 meses era a soma simples das incidências dos últimos 12 meses, reescalada para fechar com o INPC. A soma simples ignora que cada incidência está medida sobre um nível diferente do INPC, e a reescala distribuía o erro por proporção, sem base contábil.

**Evidência.** Nos últimos 24 meses, a soma simples ficava até 0,091 pp abaixo do INPC a/a no mensal (0,101 pp no quinzenal), e o fator de reescala ia de 1,012 a 1,020. Ou seja, cada parte era inflada em 1% a 2% para fechar.

**Correção.** Identidade exata, em `acrescentar_contribuicao_anual`:

```
C(i,t,h) = soma de c(i,s) × I(s−1) / I(t−h),   s de t−h+1 até t
```

Aqui c é a incidência publicada, I é o nível do INPC geral e h vale 12 meses ou 24 quinzenas. Como a soma das incidências de um período é a variação do INPC nele, a soma de um nível dá exatamente (I(t) / I(t−h) − 1) × 100. Os lags saem de uma grade de posições (coluna `posicao`, gravada pelo tratamento), e o rolling exige os h valores presentes. Se faltar incidência ou período, a contribuição fica nula.

**Antes e depois**, nível 2, em pp:

| período | componente | antes (reescalada) | depois (identidade) |
|---|---|---|---|
| ago/26 | Mercadorias | 1,2823 | 1,2899 |
| ago/26 | Serviços | 1,7060 | 1,7159 |
| ago/26 | Energia e tarifas | 0,4231 | 0,4123 |
| ago/26 | Agropecuários | −0,1496 | −0,1562 |
| 1Q set/26 | Mercadorias | 1,2106 | 1,2162 |
| 1Q set/26 | Serviços | 1,7077 | 1,7150 |
| 1Q set/26 | Energia e tarifas | 0,4652 | 0,4536 |
| 1Q set/26 | Agropecuários | 0,0370 | 0,0353 |

Nos últimos 24 meses, a diferença entre os dois métodos chegou a 0,020 pp por componente (média de 0,005 pp).

**Resíduo de fechamento sem reescala**, nos últimos 24 meses (máximo de |soma do nível − INPC a/a|):

| frequência | nível 1 | nível 2 | nível 3 |
|---|---|---|---|
| mensal | 0,0006 pp | 0,0045 pp | 0,0043 pp |
| quinzenal | 0,0011 pp | 0,0006 pp | 0,0018 pp |

É o arredondamento das incidências, que o INEGI publica com 3 casas. A etapa de métricas imprime esse resíduo em toda rodada.

**Efeito colateral, esperado.** Com a regra de janela completa, ficam nulas as contribuições anuais das janelas que passam por agosto de 2018 (incidência não publicada) e as de antes do começo de cada série de incidência: dez/2010 para 8 componentes e jun/2013 para o INPC geral. Nada disso cai na janela dos gráficos (últimos 24 meses).

## 2. Difusão

**Problema.** A difusão descartava de uma vez os itens sem variação no mês e usava esse mesmo conjunto para as medidas anuais. Um item com variação no mês, mas sem variação em 12 meses, entrava no denominador da medida anual como "não acima de 3%". Além disso, a cobertura não aparecia em lugar nenhum. O texto também tratava 3% e 4% como se fossem a meta de cada item.

**Evidência.** Desde 2019, 246 itens tinham variação anual no primeiro semestre de 2019, contra 269 com variação no mês. Os itens da cesta 2018 sem série somam 2,7% do peso.

**Correção.** Em `serie_difusao`, cada medida tem o seu conjunto válido: a alta no mês usa os itens com variação no período; as medidas acima de 3% e de 4% usam os itens com variação anual. Por mês, guardo `itens_validos_mes`, `cobertura_peso_mes`, `itens_validos_anual` e `cobertura_peso_anual`. A cobertura é o peso desses itens sobre o peso total da cesta vigente. O tooltip do gráfico mostra a cobertura. O subtítulo, os nomes das linhas e a frase de destaque dizem que 3% e 4% são a meta do Banxico para o INPC e o teto do intervalo, usados como régua.

**Antes e depois.** Nos meses recentes os números não mudam, porque a cobertura é de 100%. Em ago/26: 67,98% do peso com alta no mês, 62,28% acima de 3% e 37,15% acima de 4%, com 292 itens. As medidas de alta no mês não mudaram em nenhum mês. As anuais mudaram em 19 meses, todos entre 2019 e meados de 2020, em até 2,4 pp. Em mar/2019, por exemplo, a parte acima de 3% foi de 60,11% para 62,43%, e a acima de 4% de 45,80% para 47,57%: o denominador deixou de contar itens sem variação anual. Nesse período a cobertura mínima foi de 93,6% do peso (anual, 246 itens) e 97,3% (mensal, 269 itens).

## 3. Validação

**Problema.** Quatro buracos:
- o `max()` do Python pula NaN em silêncio (`max([0,001, nan])` dá 0,001);
- a aditividade fazia `dropna()` e, com isso, um período sem dado virava um período a menos na conta;
- os lags eram por linha, então um período intermediário ausente fazia a variação anual comparar com 13 meses atrás;
- um tabulado velho conferia com o mês velho e passava.

**Correção.** Quatro checagens em `validacao.py`, cada uma com o porquê num comentário:
1. **Base completa.** Nas janelas conferidas (24 meses mais um ano de lag), os 16 componentes do catálogo têm índice e incidência em todos os períodos, numa grade de posições. A grade vem do catálogo e da coluna `posicao`, não do que está na base, então o que sumiu aparece como buraco.
2. **Tabulado em dia.** O período do tabulado tem de ser o último da base.
3. **Último release contra o tabulado**, com os lags 1 e 12 (ou 24) tirados da grade. Um componente fora do tabulado vira nulo, e qualquer nulo na comparação é falha.
4. **Aditividade** sem `dropna`: um nulo na janela é falha.

**Testes de falha**, rodados antes e depois da mudança, com a alteração só em memória:

| caso | o que simulei | antes | depois |
|---|---|---|---|
| NaN em componente obrigatório | índice de Mercancías de jul/26 = NaN | **passou** | parou: "indice de mercancias em 2026-07" |
| componente ausente | Vivienda some em ago/26 | **passou** | parou: "indice de vivienda em 2026-08; incidencia de vivienda em 2026-08" |
| período intermediário ausente | mar/26 some de todas as séries | parou, mas com "desvio máximo 1,159 pp", sem dizer por quê | parou: "indice de indice_general em 2026-03; ... (e mais 27)" |
| tabulado atrasado | tabulado mensal de jul/26, coerente com a base | **passou** | parou: "mensal: tabulado ['2026-07'] e base 2026-08" |
| componente fora do tabulado | Vivienda some do tabulado mensal | não testado | parou: "último release vs tabulado oficial tem 3 valor(es) nulo(s) na comparação" |
| base intacta | nada | passou | passou (desvios de 0,004965 e 0,000665 pp) |

Toda falha sai com `SystemExit`, que no `run_pipeline.py` interrompe as etapas seguintes. Conferi que o processo termina com código 1, que é o que deixa o job do GitHub vermelho.

## 4. Linguagem: surpresa

**Problema.** "Surpresa" e "contribuição da surpresa" sugerem desvio contra expectativa de mercado. O número é outro: a diferença contra a mediana do mesmo mês em 2010 a 2019, vezes o peso efetivo.

**Correção.** Na tela, o card virou "Desvio em relação à mediana sazonal (2010–2019)", a coluna virou "Desvio sazonal ponderado", as seções viraram "Acima da mediana sazonal" e "Abaixo da mediana sazonal", e o destaque virou "Maior desvio sazonal". O subtítulo diz que não é expectativa de mercado e que as medianas das aberturas não somam a mediana do INPC. A coluna na base continua `contribuicao_surpresa`, para não mudar nomes de código.

**Antes e depois.** O texto antes era "Maior surpresa vs padrão sazonal: Jitomate +0,08 pp; para baixo: Gasolina de bajo octanaje −0,02 pp". Agora é "Maior desvio sazonal ponderado: Jitomate +0,08 pp; ...". Os números não mudaram.

## 5. Mensal implícito: backtest

**Problema.** O mensal implícito (1ª quinzena publicada e 2ª quinzena pela mediana histórica) aparecia como número do mês sem nunca ter sido testado.

**Método.** Para cada mês de jan/2010 a ago/2026 (200 meses), estimei a variação mensal do jeito do dashboard, mas com a mediana e os quartis da 2ª quinzena calculados só com os 10 anos anteriores àquele mês, sem informação futura. A referência é a hipótese de 2ª quinzena sem variação (índice do mês = 1ª quinzena). O erro é estimado menos realizado, em pp da variação mensal.

| série | período | n | erro médio | erro abs. médio | REQM | 2ª quinzena zero: erro médio | erro abs. médio | REQM | cobertura p25 a p75 | melhor que a referência em |
|---|---|---|---|---|---|---|---|---|---|---|
| INPC | 2010-2026 | 200 | −0,001 | 0,065 | 0,085 | −0,067 | 0,083 | 0,106 | 35% | 66% dos meses |
| INPC | 2010-2019 | 120 | +0,006 | 0,055 | 0,067 | −0,059 | 0,069 | 0,089 | 36% | 62% |
| INPC | 2020-2026 | 80 | −0,013 | 0,080 | 0,106 | −0,079 | 0,104 | 0,128 | 34% | 70% |
| Núcleo | 2010-2026 | 200 | −0,001 | 0,034 | 0,046 | −0,058 | 0,062 | 0,076 | 36% | 76% |
| Núcleo | 2010-2019 | 120 | +0,011 | 0,031 | 0,042 | −0,046 | 0,051 | 0,065 | 38% | 68% |
| Núcleo | 2020-2026 | 80 | −0,021 | 0,039 | 0,051 | −0,075 | 0,078 | 0,090 | 34% | 86% |

Com a janela fixa de produção (2010 a 2019), que não tem informação futura para os meses de 2020 em diante: INPC com erro médio de −0,020 e erro absoluto médio de 0,081 pp; núcleo com −0,027 e 0,041 pp. São números parecidos com os da janela móvel.

**Leitura.** A mediana supera a referência: o erro absoluto médio cai 22% no INPC e 45% no núcleo, e o viés praticamente some. A referência erra sistematicamente para baixo, porque a 2ª quinzena costuma subir. Por isso o cartão continua como estimativa, e não como "cenário mecânico". A faixa p25 a p75, porém, conteve o mês realizado em só 35% dos casos, abaixo dos 50% que o nome sugere. Ela mostra a dispersão histórica da 2ª quinzena, não um intervalo de confiança.

**Correção na tela.** O cartão diz "Mensal implícito (estimativa)" e "faixa p25 a p75 0,38% a 0,44%; conteve o mês realizado em 35% dos casos no backtest". O tooltip traz o erro absoluto médio contra a referência.

## 6. Estabilidade do SAAR: exercício pseudo-tempo-real

**Problema.** O STL é reestimado a cada rodada, e a ponta da série dessazonalizada muda quando entram meses novos. O dashboard mostrava o SAAR de 3 e de 6 meses sem saber quanto eles revisam.

**Método.** Para cada data de corte, reestimei o STL com a série cortada naquela data (a mesma função da etapa, desde 2000). Calculei o SAAR da ponta e comparei com o SAAR da mesma data calculado hoje, com a amostra inteira. Revisão = hoje − ponta, em pp ao ano.

| série | corte | SAAR 3m na ponta | SAAR 3m hoje | revisão 3m | SAAR 6m na ponta | SAAR 6m hoje | revisão 6m |
|---|---|---|---|---|---|---|---|
| Núcleo | 2022-06 | 6,19 | 8,07 | +1,87 | 6,21 | 7,97 | +1,75 |
| Núcleo | 2023-06 | 3,50 | 3,43 | −0,07 | 5,90 | 5,08 | −0,82 |
| Núcleo | 2024-06 | 4,92 | 2,15 | −2,78 | 5,15 | 3,23 | −1,91 |
| Núcleo | 2025-06 | 5,02 | 4,97 | −0,06 | 4,51 | 4,50 | −0,01 |
| INPC | 2022-06 | 7,48 | 9,60 | +2,12 | 7,92 | 9,60 | +1,69 |
| INPC | 2023-06 | −1,98 | 2,33 | +4,30 | 1,94 | 3,86 | +1,91 |
| INPC | 2024-06 | 5,54 | 4,65 | −0,89 | 5,02 | 4,38 | −0,64 |
| INPC | 2025-06 | 5,41 | 7,01 | +1,60 | 4,51 | 4,41 | −0,10 |

Com os 37 cortes mensais de jun/2022 a jun/2025, a revisão absoluta média foi:
- **núcleo:** 1,25 pp no 3 meses (máximo de 2,88) e 1,00 pp no 6 meses (máximo de 2,12), uma razão de 1,2;
- **INPC:** 1,67 pp (máximo de 5,72) e 1,00 pp (máximo de 2,74), uma razão de 1,7.

**Leitura e decisão.** O 3 meses revisa mais que o 6 meses nas duas séries. No núcleo, que é o que o gráfico mostra, a diferença é de 25%. É uma decisão no limite: não chega a ser "muito mais", mas o máximo é bem maior, e no INPC a razão é de 1,7. Dei destaque ao 6 meses (linha grossa, primeiro na legenda) e deixei o 3 meses em linha fina, com o nome "SAAR 3 meses (revisa mais)". A nota de fim de amostra traz os números acima. O ponto que mais importa é outro: até o 6 meses revisa 1 pp em média, então a ponta do SAAR é indicação de direção, não um número firme.

## 7. Justificativa do quinzenal

**Problema.** A documentação dizia que o quinzenal não era dessazonalizado porque "os métodos padrão não lidam com 24 períodos por ano". Não é verdade para o STL, que aceita período 24. Quem não aceita é o X-13, que só trabalha com dado mensal ou trimestral.

**Correção.** Corrigi o texto em `dessazonalizacao.py`, no guia e na metodologia. Não dessazonalizar o quinzenal passa a ser escolha: o mensal é a média das duas quinzenas e o ritmo é lido nele; para a quinzena, a leitura sazonal é a comparação com a mediana histórica.

## 8. Card vazio e workflow

**Problema.** A aba "Fontes externas" tinha só um card "Em construção". O `.github/workflows/atualizar_inpc.yml` tinha duas linhas de comentário e nenhum passo.

**Correção.** O card saiu e, com ele, a aba, que ficaria vazia. O workflow agora tem só disparo manual (`workflow_dispatch`), sem publicação automática:
- instala o Python 3.12 e o `requirements.txt`;
- roda `python run_pipeline.py`; com a base vazia, a ingestão baixa o histórico completo;
- falha se a validação falhar, porque o `SystemExit` sai com código 1;
- guarda `dashboard_inpc.html` como artefato e, mesmo em falha, o `validacao.json` quando ele existir.

**Limite.** O arquivo YAML é válido, mas o workflow não foi executado no GitHub, porque este trabalho foi feito sem push. Não sei se o INEGI responde bem a IPs do GitHub; se bloquear, o job falha na ingestão, com a mensagem de rede.

## Rodadas completas

A preencher com a saída das rodadas do zero e incremental.

## O que continua em aberto

- A validação confere a base contra o INEGI e contra identidades. Ela não confere as métricas analíticas (difusão, desvio sazonal, SAAR), que dependem de escolhas metodológicas documentadas aqui e na `metodologia.md`.
- A faixa do mensal implícito é estreita (35% de cobertura). Uma faixa honesta de 50% precisaria vir dos erros do backtest, e não dos quartis da mediana; não mudei o cálculo.
- A ponta do SAAR revisa perto de 1 pp em média, mesmo no 6 meses.
- O workflow não foi testado no GitHub.
- O número de genéricos na cesta 2024 (292) está fixo no código da ingestão; se o INEGI mudar a cesta, a ingestão para com mensagem, de propósito.
