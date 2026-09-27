# Metodologia

Registro das escolhas de método e dos fatos que descobri nos dados do INEGI, com a evidência de cada um.

## Fonte dos dados

Todos os números vêm do INEGI, sem token:

- App "Índices de precios" (indicesdeprecios): os 16 componentes do INPC (geral, subyacente, no subyacente, os 4 grupos e os 9 subíndices), as 16 incidências e os índices dos 292 genéricos, em frequência mensal e quinzenal. É a única fonte oficial com os subíndices e os genéricos com histórico.
- Planilhas de ponderadores: a cesta 2024 (vigente desde a 2ª quinzena de julho de 2024) e a cesta 2018 (da 2ª quinzena de julho de 2018 até a 1ª quinzena de julho de 2024). As planilhas marcam com um X o subíndice de cada genérico; essa é a classificação oficial que uso.
- Tabulados CA55 (mensal) e CA56 (quinzenal): os números que o INEGI publica no release. São o gabarito da validação.

A API do Banco de Indicadores (BIE) foi testada como segundo canal. Ela entrega os mesmos números que o app (na auditoria final, idênticos em todo o histórico dos 7 componentes que ela tem), mas não tem os subíndices nem os genéricos, e por isso saiu do pipeline.

## Fatos sobre os dados

- O índice mensal é a média das duas quinzenas. No INPC geral isso vale desde 1988 (desvio máximo de 0,0005, arredondamento). Nos outros 15 componentes, vale a partir de março de 1995; antes, as séries foram retropoladas pelo INEGI e desviam até 0,03 da média.
- O INEGI não publica as incidências mensais de agosto de 2018, o mês da troca de base (2ª quinzena de julho de 2018 = 100); o tabulado avisa que o cálculo desse mês "se ve afectada". Na base, esse mês fica nulo.
- Em janeiro de 2011 as incidências não fecham com a inflação: a soma dos 9 subíndices desvia 0,0128 pp da variação do INPC. É o único caso acima de 0,01 pp desde 2002 e coincide com a entrada da base 2010.
- 15 genéricos foram criados na cesta 2024 e não têm histórico anterior a julho de 2024: 033 Leche evaporada y condensada, 087 Cilantro, epazote y perejil, 090 Leche maternizada y alimentos para bebé, 101 Bebidas energéticas, 130 Complementos de vestir, 141 Servicios para el mantenimiento, reparación y seguridad de la vivienda, 143 Otros servicios relacionados con la vivienda, 149 Muebles diversos para el hogar, 155 Toallas, cortinas y otros blancos, 170 Herramientas y equipo para el hogar, 237 Streaming de películas y música, 246 Servicios recreativos y centros nocturnos, 247 Instrumentos musicales, y descargas de audio y video, 249 Museos y sitios culturales e 250 Paquetes para fiesta.
- Os genéricos reproduzem o INPC: agregados com os ponderadores 2024 (Laspeyres encadeado), o INPC geral e os 9 subíndices saem com erro de até 0,0004% no nível desde a 2ª quinzena de julho de 2024.
- O fator de encadeamento da planilha 2024 é o índice da 2ª quinzena de julho de 2024 dividido por 100, para cada genérico e cada agregado (INPC: 136,095 / 100). É o que liga a cesta 2024 ao histórico.
- Na cesta 2018, 28 genéricos não existem mais na cesta 2024. Os outros casam pelo nome e recebem o código atual; esses 28 ficam sem código.
- Nem toda incidência começa em 2002. As incidências mensais de 8 componentes (subyacente, no subyacente, mercancías, mercancías no alimenticias, servicios, otros servicios, energéticos y tarifas e tarifas autorizadas) só existem a partir de dezembro de 2010, e a do INPC geral a partir de junho de 2013. A contribuição anual dessas séries antes disso fica nula, porque exijo a janela completa.
- No tabulado CA55, o "esquema 1" devolve o mesmo mês do "esquema 4": como o release anterior também publicou o mês corrente, não há como obter do INEGI o gabarito do penúltimo mês. No CA56, o esquema 1 devolve de fato a quinzena anterior.

## Escolhas

- Atualização por janela. No dia a dia, o pipeline só vai à rede se o calendário diz que saiu dado novo. Nesse caso, rebaixa os últimos 6 meses de todas as séries e sobrescreve esses períodos; releases esquecidos se fecham sozinhos. Se a base está mais de 6 meses atrasada, baixa o histórico completo.
- Validação sem nulo. As quatro checagens estão na seção 7 do guia. Qualquer valor comparado que falte é falha: o `max()` do Python pula NaN, e um `dropna` esconderia uma lacuna.
- Contribuição anual pela identidade exata: C(i,t,h) = soma de c(i,s) × I(s−1) / I(t−h), com s de t−h+1 até t, c a incidência publicada e I o nível do INPC (h = 12 meses ou 24 quinzenas). Somando um nível, dá a variação do INPC em 12 meses; sem reescala, o resíduo nos últimos 24 meses ficou abaixo de 0,0045 pp, que é arredondamento das incidências. Bate com a incidência anual do comunicado do INEGI a menos de 0,0005 pp. Substituiu a soma simples reescalada, que distorcia cada parte em até 0,02 pp.
- Difusão com conjunto válido por medida. A alta no mês usa os itens com variação no período; a de 3% em 12 meses, os itens com variação anual. Guardo o número de itens válidos e a cobertura do peso da cesta vigente. Desde 2019, a cobertura mínima foi de 93,6% (anual) e 97,3% (mês), por itens da cesta 2018 sem série e, na anual, por itens ainda sem 12 meses de história. O corte é um só, 3%, a meta do Banxico para o INPC, usada como régua: item não tem meta.
- Desvio sazonal, não surpresa. O desvio sazonal ponderado é o peso efetivo vezes a diferença entre a variação e a mediana do mesmo mês (ou quinzena) em 2010 a 2019. Não é surpresa contra expectativa de mercado, e as medianas não somam: os desvios das aberturas não somam o desvio do INPC.
- Estimativa do mês, com faixa pelos erros. Backtest sem informação do futuro desde jan/2010 (a mediana de cada mês usa só os 10 anos anteriores), 200 meses: no INPC, erro médio −0,001 pp e erro absoluto médio 0,065 pp, contra −0,067 e 0,083 pp de supor a 2ª quinzena sem variação; no núcleo, −0,001 e 0,034 pp contra −0,058 e 0,062 pp. Como supera a referência, fica como estimativa. A faixa antiga, p25 a p75 da alta da 2ª quinzena, conteve o mês realizado em só 35% (INPC) e 36% (núcleo) dos meses. Por isso a faixa passou a ser a estimativa mais os quartis 25 e 75 dos erros do próprio método de 2020 em diante, onde a mediana de 2010 a 2019 só usa passado; fora da amostra, ela conteve o realizado em 50,0% (INPC) e 48,2% (núcleo) de 56 meses.
- SAAR: os últimos pontos mudam. O STL reestima os fatores sazonais a cada mês novo, então a ponta da série ajustada, e do SAAR, muda. Num exercício pseudo-tempo-real com o STL reestimado em 37 cortes mensais de jun/2022 a jun/2025, a ponta do SAAR do núcleo mudou em média 1,25 pp (3 meses) e 1,00 pp (6 meses); a do INPC, 1,67 e 1,00 pp. Por isso o de 6 meses é o de destaque. O dashboard não traz essa nota.
- O quinzenal não é dessazonalizado, por escolha. O STL aceitaria período 24 (quem não aceita é o X-13, só mensal ou trimestral), mas o mensal já é a média das duas quinzenas e é nele que o ritmo é lido. Para a quinzena, a leitura sazonal é a comparação com a mediana histórica.
