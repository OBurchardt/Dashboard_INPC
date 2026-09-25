# Metodologia

Registro das escolhas metodológicas e dos fatos descobertos nos dados do INEGI, com a evidência de cada um. Atualizado ao longo do projeto.

## Fonte dos dados

Todos os números vêm do INEGI, sem token:

- **App "Índices de precios"** (indicesdeprecios): os 16 componentes do INPC (geral, subyacente, no subyacente, os 4 grupos e os 9 subíndices), as 16 incidências e os índices dos 292 genéricos, em frequência mensal e quinzenal. É a única fonte oficial com os subíndices e os genéricos com histórico.
- **Planilhas de ponderadores**: a cesta 2024 (vigente desde a 2ª quinzena de julho de 2024) e a cesta 2018 (da 2ª quinzena de julho de 2018 até a 1ª quinzena de julho de 2024). As planilhas marcam com um X o subíndice de cada genérico; essa é a classificação oficial usada no projeto.
- **Tabulados CA55 (mensal) e CA56 (quinzenal)**: os números que o INEGI publica no release. Servem de gabarito para a validação.

A API do Banco de Indicadores (BIE) foi testada como segundo canal. Ela entrega os mesmos números que o app (diferença máxima de 0,0005 no índice, só por arredondamento), mas não tem os subíndices nem os genéricos, e por isso saiu do pipeline.

## Fatos sobre os dados

- **O índice mensal é a média das duas quinzenas.** No INPC geral isso vale desde 1988 (desvio máximo de 0,0005, só arredondamento). Nos outros 15 componentes, vale a partir de março de 1995. Antes disso, as séries dos componentes foram retropoladas pelo INEGI e desviam até 0,03 da média das quinzenas.
- **O INEGI não publica as incidências mensais de agosto de 2018.** Foi o mês da troca de base (2ª quinzena de julho de 2018 = 100), e o tabulado oficial avisa que o cálculo da incidência desse mês "se ve afectada". Na base, esse mês fica como nulo.
- **Em janeiro de 2011 as incidências não fecham com a inflação.** A soma das incidências dos 9 subíndices desvia 0,0128 ponto percentual da variação do INPC geral. É o único caso acima de 0,01 pp em 565 períodos desde 2002 e coincide com a entrada da base 2010 (2ª quinzena de dezembro de 2010).
- **15 genéricos foram criados na cesta 2024 e não têm histórico anterior a julho de 2024.** São eles: 033 Leche evaporada y condensada, 087 Cilantro, epazote y perejil, 090 Leche maternizada y alimentos para bebé, 101 Bebidas energéticas, 130 Complementos de vestir, 141 Servicios para el mantenimiento, reparación y seguridad de la vivienda, 143 Otros servicios relacionados con la vivienda, 149 Muebles diversos para el hogar, 155 Toallas, cortinas y otros blancos, 170 Herramientas y equipo para el hogar, 237 Streaming de películas y música, 246 Servicios recreativos y centros nocturnos, 247 Instrumentos musicales, y descargas de audio y video, 249 Museos y sitios culturales e 250 Paquetes para fiesta.
- **Os genéricos reproduzem o INPC.** Agregando os 292 genéricos com os ponderadores 2024 (Laspeyres encadeado), o INPC geral e os 9 subíndices saem com erro de até 0,0004% no nível, desde a 2ª quinzena de julho de 2024.
- **O fator de encadeamento da planilha 2024 é o índice da 2ª quinzena de julho de 2024 dividido por 100.** Vale para cada genérico e para cada agregado (por exemplo, INPC: 136,095 / 100 = 1,36095). É o que liga a cesta 2024 ao histórico da cesta 2018.
- **Na cesta 2018, 28 genéricos não existem mais na cesta 2024.** Os outros casam pelo nome e recebem o código atual. Esses 28 ficam sem código e são identificados pelo nome.
- **No tabulado CA55, o "esquema 1" devolve o mesmo mês do "esquema 4".** O esquema 1 é o estado do release anterior; como o release anterior também publicou o mês corrente, não há como obter do INEGI o gabarito do penúltimo mês. No CA56 (quinzenal), o esquema 1 devolve de fato a quinzena anterior.

## Escolhas de processamento

- **Atualização por janela.** No dia a dia, o pipeline só vai à rede se o calendário diz que saiu dado novo. Nesse caso, rebaixa os últimos 6 meses de todas as séries e sobrescreve esses períodos na base; releases esquecidos se fecham sozinhos. Se a base está mais de 6 meses atrasada, baixa o histórico completo.
- **Validação.** Duas checagens, com tolerância de 0,01 ponto percentual: (1) a variação no período, a variação anual e a incidência dos 16 componentes, calculadas da base, batem com o tabulado oficial do último release; (2) nos últimos 24 meses, a incidência da subyacente mais a da no subyacente soma a variação do INPC geral.
