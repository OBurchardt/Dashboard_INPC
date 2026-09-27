# Guia do projeto

Escrevi este guia para quem abre a pasta pela primeira vez, inclusive eu daqui a uns meses. Ele explica o que cada peça faz, de onde vem cada número e onde mexer quando algo precisar mudar. A árvore de pastas está no README; as escolhas de método e a evidência de cada uma estão em `metodologia.md`; a conferência com o INEGI e o Banxico está em `auditoria.md`. Os exemplos usam o release da 1ª quinzena de setembro de 2026, divulgado em 24/09/2026 às 06:00 da Cidade do México.

## 1. O que o projeto faz

Baixa do INEGI as séries do INPC, o índice de preços ao consumidor do México, confere com o que o próprio INEGI publicou no release, faz as contas que um economista quer ver no dia e junta tudo num único HTML que abre sem internet. Às 06:00 da Cidade do México sai o dado, alguém roda `python run_pipeline.py` e, em poucos minutos, tem a inflação cheia e a do núcleo contra a meta do Banxico, de onde veio a alta, o que fugiu do normal daquela época do ano e se o ritmo está acelerando.

Tudo vem do INEGI, sem chave de API: o app "Índices de Precios", os xlsx de ponderadores e os tabulados do release são públicos. A única exceção é a expectativa do destaque "Realizado x expectativa" (seção "Fontes" do README): digitada à mão, ou a Pesquisa do Banxico, que precisa de um token gratuito no `.env`.

No release de exemplo, o painel abre assim:

- INPC 0,33% na quinzena e 3,42% em 12 meses, 0,16 pp acima da 1ª quinzena de agosto (3,26%).
- Núcleo 0,17% e 3,79% (0,14 pp abaixo dos 3,93% da 1ª quinzena de agosto); serviços 4,33% e mercadorias 3,22% em 12 meses; não núcleo 2,17%.
- Realizado x expectativa: com a Encuesta Citi digitada em `config/expectativas_manuais.csv`, "INPC 0,33% vs 0,28% esperado (+0,05 pp)" e "Núcleo 0,17% vs 0,19% esperado (−0,02 pp)"; sem linha manual, "Sem expectativa cadastrada para 1ª quinz. set/26".
- Estimativa para setembro: 0,42% no mês e 3,45% em 12 meses, intervalo provável de 0,37% a 0,50%.
- Maior contribuição: Jitomate, +0,11 pp (o preço subiu 22,79% na quinzena).
- Maior desvio sazonal ponderado: Jitomate, +0,08 pp; para baixo, Gasolina de bajo octanaje, −0,02 pp.
- 62% do peso da cesta com inflação acima de 3% em 12 meses (ago/26).

### Vocabulário

A tela é para leitor brasileiro e não usa os termos do INEGI. No código, nas colunas e neste guia continuo com os termos das fontes:

| no código e no INEGI | na tela |
|---|---|
| incidência | contribuição (pp da variação do INPC no período) |
| genérico | abertura |
| subíndice | grupo |
| norma sazonal | padrão sazonal, ou mediana sazonal (mediana de 2010 a 2019) |
| subyacente / no subyacente | Núcleo / Não núcleo (o nome oficial fica num tooltip) |

Os nomes das aberturas ficam em espanhol, como o INEGI publica (Jitomate, Cebolla). Os nomes dos componentes estão em `NOMES_EXIBICAO`, no `config/parametros.py`. Variações e contribuições saem sempre com 2 casas.

## 2. Como rodar

Numa máquina nova:

```
python -m venv .venv
.venv\Scripts\activate          (no Linux e no Mac: source .venv/bin/activate)
pip install -r requirements.txt
python run_pipeline.py
```

As versões do `requirements.txt` são fixas e foram testadas com Python 3.12.4. A única opção fica no topo do `run_pipeline.py`:

- `IMPORTAR_DO_ZERO = False` é o uso de todo dia. A ingestão compara o calendário com a base. Se não saiu nada novo, nem vai à rede, imprime "Já atualizado" e as outras etapas refazem o dashboard em uns 12 segundos. Se saiu, rebaixa só os últimos 6 meses e sobrescreve esses períodos, o que também pega revisões do INEGI.
- `True` rebaixa o histórico inteiro, de 1970 até hoje. Num clone limpo levou uns 5 minutos, quase tudo na ingestão. Na primeira vez nem precisa: com a base vazia, ou atrasada mais de 6 meses, a ingestão já baixa tudo sozinha.

No dia do release, basta rodar a partir das 06:00 da Cidade do México; antes disso a ingestão considera que o dado ainda não saiu, porque lê o calendário no fuso de lá. O HTML fica em `output/dashboard_inpc.html` (e igual em `output/index.html`, que é o que o site serve).

Cada etapa também roda sozinha (`python pipeline/2_analise/tabelas.py`), desde que as anteriores já tenham gerado os arquivos de que ela precisa. Se a validação falhar, o pipeline para antes da montagem e o dashboard anterior continua lá: prefiro mostrar o dashboard de ontem a um número errado.

## 3. Fluxo dos dados

```
INEGI
 ├─ app Índices de Precios (árvore + exportador CSV)
 ├─ xlsx de ponderadores 2018 e 2024
 └─ tabulados CA55 (mensal) e CA56 (quinzenal)
        │
        ▼  ingestao.py
data/raw/
  arvore_genericos_{mensal,quinzenal}.json
  componentes_, incidencias_, genericos_{mensal,quinzenal}.csv
  ponderadores_2018.xlsx, ponderadores_2024.xlsx
  tabulado_{mensal,quinzenal}.json
        │
        ▼  tratamento.py
data/processed/  series, genericos, ponderadores, tabulado_oficial (.parquet)
        │
        ▼  validacao.py  ──►  validacao.json   (se falhar, para aqui)
        ▼  dessazonalizacao.py  ──►  series_dessazonalizadas.parquet
        ▼  metricas.py  ──►  metricas_componentes, _genericos, _difusao, _aberturas (.parquet), metricas_resumo.json
        ├─►  tabelas.py   ──►  tabelas.json
        └─►  graficos.py  ──►  graficos.json
                 ▼  montagem.py (+ template.html + plotly.js + calendário)
output/dashboard_inpc.html e index.html
```

As etapas só conversam por arquivos: nenhuma importa função de outra, todas importam só o `config/parametros.py`. É por isso que dá para rodar uma etapa sozinha.

## 4. Arquivo por arquivo

### run_pipeline.py

Lista as oito etapas e roda cada uma com `runpy.run_path`, passando `importar_do_zero` para dentro dela (só a ingestão usa). A ordem das etapas é a documentação do fluxo.

### config/parametros.py

As constantes que eu posso querer mudar, em seções: caminhos (importar o arquivo já cria as pastas), fuso e janela de atualização, rede (3 tentativas, 120 s, lotes de 120 ids), URLs, os ids das estruturas do app que achei navegando nele (`112001700010` é o índice mensal dos 16 componentes, `112001600020` o quinzenal, `112001800030` e `112001800020` as incidências; as árvores `112001700030` e `112001600030` são as únicas que descem até os 292 genéricos), os nomes da tela e as janelas das análises (dessazonalização desde 2000, norma de 2010 a 2019, gráficos desde 2019, mês-base do não núcleo em jul/2024, 4 aberturas por subíndice, tolerância de 0,01 pp).

### pipeline/1_dados/ingestao.py

- `pedir`: GET ou POST com até 3 tentativas. É a única tolerância a erro do projeto, porque o servidor do INEGI derruba conexão.
- `periodo_padrao`: converte o rótulo do INEGI para o meu formato ("2026-08" e "2026-09-Q1"), que ordena certo como texto.
- `filhos_do_no`, `varrer_arvore`, `baixar_arvore`: percorrem a árvore do app nó por nó (o serviço devolve HTML). Se vierem menos de 292 genéricos, varro de novo; se continuar faltando, paro.
- `ler_csv_exportador`, `exportar`: pedem ao exportador as séries de uma estrutura entre dois anos. O CSV vem em Windows-1252, com um cabeçalho solto; os dados começam na linha "Fecha".
- `conjuntos_de_series`, `salvar_tabela`: as seis tabelas (componentes, incidências e genéricos, em mensal e quinzenal). Na atualização, os períodos que chegaram substituem os mesmos períodos da base.
- `baixar_ponderadores`, `baixar_tabulados`: os dois xlsx e os dois tabulados do release.
- `ultimo_divulgado`, `ultimo_na_base`: o que o calendário diz que já saiu e o que a base tem. Cuidado: o release "mensal" traz também a 2ª quinzena do mesmo mês.
- `baixar_historico_completo`, `atualizar`, `avisar_se_o_calendario_acabou`: os dois modos e o aviso de que o calendário acabou.
- `token_do_banxico`, `baixar_expectativas_banxico`: a mediana da inflação mensal esperada na Pesquisa do Banxico (INPC e núcleo, séries SR14223 e SR14314 do SIE), para `data/raw/expectativas_banxico.csv`. Roda a cada execução, porque a pesquisa sai no começo do mês, fora do calendário do INEGI. Sem token, ou com a API fora, imprime um aviso e o pipeline segue: é a única falha que passa, porque a validação do INEGI não pode depender do Banxico.

### pipeline/1_dados/tratamento.py

Passa o bruto para parquet longo (uma linha por série e período). `normalizar` tira acento e pontuação dos nomes, porque o INEGI escreve o mesmo nome de jeitos diferentes em cada arquivo. `rotulos_do_periodo` dá os três rótulos da tela ("1ª quinz. set/26", "1ª q. set", "set/26"), `data_do_periodo` põe a 1ª quinzena no dia 1 e a 2ª no dia 16, e `posicao_do_periodo` numera os períodos de 1 em 1, para um lag ser uma subtração e um período ausente virar buraco. `ler_planilha_ponderadores` lê o X que marca o subíndice de cada genérico na planilha do INEGI; o código do genérico vem do nome casado com a árvore.

### pipeline/1_dados/validacao.py

As quatro checagens da seção 7. Recalcula as variações sozinha, sem a etapa de métricas, para ser um teste independente.

### pipeline/1_dados/dessazonalizacao.py

`dessazonalizar` aplica o STL do statsmodels no log do índice mensal, com ciclo de 12 meses e a opção robusta a outliers, de 2000 para cá: índice sem sazonalidade = exp(log(índice) − componente sazonal). O quinzenal não é dessazonalizado (a razão está na metodologia).

### pipeline/2_analise/metricas.py

Todas as fórmulas estão aqui.

Variações (`acrescentar_variacoes`):

```
variação no período = (Iₜ / Iₜ₋₁ − 1) × 100
variação anual      = (Iₜ / Iₜ₋ₙ − 1) × 100,   n = 12 no mensal, 24 no quinzenal
```

Norma sazonal (`acrescentar_norma`): para cada série e posição no ano ("09" ou "09-Q1"), mediana, p25 e p75 da variação no período entre 2010 e 2019. Uso a mediana porque a janela tem choques, como a liberalização da gasolina em janeiro de 2017. No exemplo, o INPC subiu 0,33% e a norma da 1ª quinzena de setembro é 0,32% (p25 0,23%, p75 0,34%).

Incidência: a dos componentes é a série que o INEGI publica. A dos genéricos eu calculo com o peso efetivo (`peso_efetivo_do_generico`). Na cesta 2024, o INPC é a média ponderada dos genéricos, cada índice dividido pelo seu fator de encadeamento (o índice da 2ª quinzena de julho de 2024 dividido por 100):

```
relativo do genérico = índice do genérico / fator de encadeamento
relativo do INPC     = INPC / (INPC da 2Q jul/2024 / 100)
peso efetivo         = ponderador × relativo do genérico (t−1) / relativo do INPC (t−1) / 100
incidência           = peso efetivo × variação no período
```

Com o jitomate na 1ª quinzena de setembro: ponderador 0,7892, fator 2,4055, índice de 150,821 na 2ª quinzena de agosto (relativo 62,70); INPC de 145,531 e 136,095 na 2Q jul/2024 (relativo 106,93); peso efetivo 0,7892 × 62,70 / 106,93 / 100 = 0,00463; com alta de 22,79%, a incidência é 0,105 pp, o que o INEGI publica. Um item que subiu mais que o INPC desde julho de 2024 passa a pesar mais que na planilha. Antes da cesta 2024 os pesos eram outros, então não calculo incidência de genérico antes dela.

Desvio sazonal ponderado (coluna `desvio_sazonal_ponderado`) = peso efetivo × (variação − mediana sazonal). O jitomate subiu 22,79% contra uma mediana de 5,46%: 0,00463 × 17,33 = 0,080 pp. Multiplicar pelo peso evita que frutas e verduras dominem a lista só por oscilarem muito.

Contribuição para a inflação em 12 meses (`acrescentar_contribuicao_anual`). A incidência c(s) são pontos da variação do INPC no período s, medidos sobre o nível I(s−1). Para somar períodos diferentes, levo todos para a base do começo da janela:

```
C(t) = soma de c(s) × I(s−1) / I(t−h),   s de t−h+1 até t,   h = 12 meses ou 24 quinzenas
```

Somando um nível, isso é exatamente a variação do INPC em 12 meses. Em agosto de 2026: Mercadorias 1,29 pp, Serviços 1,72 pp, Energia e tarifas 0,41 pp e Agropecuários −0,16 pp, somando 3,26%. São os números da incidência anual do comunicado do INEGI.

Contribuição para o pai (`contribuicao_na_base`, `acrescentar_contribuicao_no_pai`). Para saber quanto um filho soma à variação em 12 meses do pai, como o Banxico mostra no Informe Trimestral, troco a base:

```
contribuição no pai(filho) = contribuição anual(filho) × variação anual(pai) / soma das contribuições anuais dos irmãos
```

Na 1ª quinzena de agosto de 2026: serviços 4,34% = habitação 1,63 + educação 0,39 + outros 2,32, como no Informe. A coluna `contribuicao_no_grupo` é a mesma conta para o núcleo ou o não núcleo; dela sai o gráfico do não núcleo desde jul/2024. `conferir_contribuicao_no_pai` para o pipeline se, nos últimos 24 meses, os filhos não somarem o pai a menos de 0,01 pp.

Aberturas dos subíndices (`aberturas_dos_subindices`): as 4 aberturas de maior peso na cesta 2024 e "Demais" (o subíndice menos as 4). A contribuição de cada genérico sai da mesma identidade, a partir da incidência com o peso efetivo, e vai para a base do subíndice pela mesma troca. Como essa incidência só existe na cesta 2024, as barras começam em ago/2025.

Ritmo dessazonalizado (`acrescentar_ritmo_dessazonalizado`), sobre o índice sem sazonalidade:

```
variação mensal SA = (SAₜ / SAₜ₋₁ − 1) × 100
SAAR de m meses    = ((SAₜ / SAₜ₋ₘ)^(12/m) − 1) × 100,   m = 3 ou 6
```

O núcleo de agosto tem SAAR de 6 meses de 3,90% e de 3 meses de 4,03%, contra 3,88% em 12 meses.

Difusão (`serie_difusao`): mês a mês, a parte do peso da cesta em genéricos com alta no mês e com alta acima de 3% em 12 meses, com os pesos da cesta que valia na época. Cada medida usa só os itens que têm o dado dela, e a tabela guarda o número de itens e a cobertura do peso. Em agosto de 2026: 68% subiu no mês e 62% está acima de 3%, com cobertura de 100%.

Estimativa do mês (`mensal_implicito`, `erros_do_mensal_implicito`, `cobertura_fora_da_amostra`). No dia da 1ª quinzena o mês ainda não existe, mas o índice mensal é a média das duas quinzenas:

```
índice do mês = (1ª quinzena + 1ª quinzena × (1 + mediana da alta da 2ª quinzena)) / 2
```

Em setembro: 1ª quinzena 146,010; mediana da 2ª quinzena de setembro de 0,083%, o que dá 146,132; média 146,071; contra agosto (145,462), 0,42% no mês e 3,45% em 12 meses. A faixa é a estimativa mais os quartis 25 e 75 dos erros do próprio método de 2020 em diante: 0,37% a 0,50% no INPC e 0,22% a 0,27% no núcleo. O backtest e a cobertura estão na metodologia.

Resumo (`numeros_principais`, `expectativa`, `destaques`): o `metricas_resumo.json` guarda o que vai no topo do painel, com 6 casas; o arredondamento fica para a tela. Para o INPC, o núcleo, o não núcleo, serviços e mercadorias, `numeros_principais` guarda a variação no período, o padrão sazonal, a taxa em 12 meses e a taxa em 12 meses de um mês antes, que é a comparação que o mercado faz: num release de 1ª quinzena, a 1ª quinzena do mês anterior (duas quinzenas antes); num release mensal, o mês anterior. Uma decisão acontece aqui e só aqui: se o último quinzenal termina em "Q1", o release é de 1ª quinzena e o dado principal é quinzenal; senão, é o mês. As etapas seguintes só leem `frequencia_do_release`. `expectativa` junta o realizado no período com a expectativa de cada indicador: primeiro a linha de `config/expectativas_manuais.csv` daquele período; senão, num release mensal, a pesquisa do Banxico daquele mês (a pesquisa de agosto sai no 1º dia útil de setembro, antes do INPC de agosto); senão, nada.

### pipeline/2_analise/tabelas.py

`celula_numero` formata com vírgula, 2 casas e o sinal de menos tipográfico; o que arredonda para zero sai "0,00", sem sinal e sem cor. `main_ultimos_periodos` (a tabela "Último release"), `main_top_incidencias` e `decomp_desvios` só escolhem e formatam; as duas últimas levam o período num atributo `data-periodo`, que vira o chip do card.

### pipeline/2_analise/graficos.py

As figuras saem sem estilo: cada traço leva em `meta` o componente e o papel (pai ou filho), e o template decide a cor por isso. No fim do arquivo, um dicionário liga cada figura ao `data-card` do seu espaço no template. Os pares no formato do Banxico saem de duas funções, `par_anual(pai, filhos)` e `par_contribuicoes(pai, filhos)`, que servem aos 10 gráficos de `grupos` e às 16 categorias de `explorar`. Em release de quinzena, cada série ganha um ponto depois do último mês com a última quinzena. Nos gráficos tudo sai em %, inclusive as contribuições, como no Informe; só o treemap fica em pp.

### pipeline/3_dashboard/montagem.py

`numero` é o formatador dos cartões; `releases` e `proximo_release` leem o calendário; `kpi` monta um cartão, com a mudança em 12 meses calculada entre as duas taxas já arredondadas (3,79% − 3,93% = −0,14 pp, a conta que o leitor faz com os números publicados); `mensal_implicito` formata a estimativa do próximo número mensal; `cabecalho` e `destaques` escrevem a faixa do release, os cartões e as quatro frases do topo. No fim, os dados e o plotly.js são colados no template e o HTML é gravado em `output/`.

### pipeline/3_dashboard/template.html

HTML, CSS e JavaScript num arquivo só. Toda cor sai de uma paleta fechada de 17 tokens `--p-*` no topo do `:root` (azuis, neutros e o vermelho e o verde de sinal); o resto é `var(--p-...)`. Cada componente tem uma cor só, em todas as abas: o pai é sempre marinho, e os filhos seguem azul vivo, ardósia, azul médio e ardósia escura. Nas barras empilhadas a ordem alterna claro e escuro (azul médio, azul claro, azul-noite, azul vivo; "Demais" em cinza), porque barras finas de claridade parecida "vibram". Vermelho e verde ficam só em pílulas e tabelas. O JavaScript lê `window.DADOS`, preenche a faixa e os cartões e aplica o estilo a cada figura conforme o `meta`.

## 5. Dicionário de dados

### data/raw

| arquivo | o que tem |
|---|---|
| `componentes_{freq}.csv` | uma linha por período, uma coluna por id; índices dos 16 componentes. Mensal desde 1970-01, quinzenal desde 1988-01-Q1 |
| `incidencias_{freq}.csv` | o mesmo formato; incidências dos 16 componentes, em pp. Desde 2002 |
| `genericos_{freq}.csv` | o mesmo formato; índices dos 292 genéricos |
| `arvore_genericos_{freq}.json` | os 463 nós da árvore: `id_no`, `nome`, `id_serie`, `generico`, `id_pai`, `nivel` |
| `ponderadores_2018.xlsx`, `ponderadores_2024.xlsx` | as planilhas oficiais, sem alteração |
| `tabulado_{freq}.json` | a resposta do tabulado do release mais o meu `periodo` |
| `expectativas_banxico.csv` | `periodo` (mês da pesquisa), `indicador`, `variacao_esperada`: a mediana da inflação mensal esperada, desde 1999 |

Os valores ficam como texto, com "N/E" onde o INEGI não publica; os CSVs abrem direto no Excel.

### data/processed

series.parquet: componentes e incidências, uma linha por série e período.

| coluna | significado |
|---|---|
| `id_serie` | id do INEGI |
| `tipo` | "indice" ou "incidencia" |
| `componente`, `nivel`, `pai` | nome interno, nível na hierarquia (0 a 3) e componente de cima |
| `frequencia` | "mensal" ou "quinzenal" |
| `periodo` | "2026-08" ou "2026-09-Q1" |
| `posicao` | número do período, de 1 em 1 dentro de cada frequência |
| `rotulo_periodo`, `rotulo_curto`, `rotulo_mes` | "1ª quinz. set/26", "1ª q. set", "set/26" |
| `data` | dia 1, ou dia 16 na 2ª quinzena |
| `valor` | índice (base 2Q jul/2018 = 100) ou incidência em pp |

genericos.parquet: `codigo_generico`, `nome_generico`, `subindice`, `componente_nivel2`, `componente_nivel1`, `frequencia`, `periodo`, `posicao`, os três rótulos, `data` e `indice`.

ponderadores.parquet: `cesta` ("2018" ou "2024"), `codigo_generico` (nulo nos 28 genéricos da cesta 2018 que saíram), `nome_generico`, `ponderador` (em %, soma 100 em cada cesta), `subindice`, `componente_nivel2`, `componente_nivel1`, `fator_encadeamento` (só na 2024), `vigencia_inicio`, `vigencia_fim`.

tabulado_oficial.parquet: `frequencia`, `periodo`, `componente`, `variacao`, `variacao_anual`, `incidencia`; 16 linhas por frequência, só do último release.

series_dessazonalizadas.parquet: `componente`, `periodo`, `data`, `indice_sa`. Só o mensal, desde 2000.

metricas_componentes.parquet: as colunas de identificação de `series` mais `indice`, `variacao_periodo`, `variacao_anual`, `incidencia_periodo`, `contribuicao_anual`, `contribuicao_no_pai`, `contribuicao_no_grupo`, `norma_mediana`, `norma_p25`, `norma_p75`, `norma_n` (anos de 2010–2019 no padrão), `desvio_norma`, `variacao_sa_mensal`, `saar_3m` e `saar_6m` (as três últimas só no mensal). Variações em %, incidências e contribuições em pp.

metricas_genericos.parquet: os últimos 24 meses de cada genérico, com `variacao_periodo`, `variacao_anual`, `norma_mediana`, `norma_p25`, `norma_p75`, `norma_n`, `desvio_norma`, `incidencia_periodo` e `desvio_sazonal_ponderado`.

metricas_difusao.parquet: mensal, desde 2019: `pct_genericos_em_alta` (por contagem), `pct_cesta_em_alta` e `pct_cesta_anual_acima_3` (por peso), e para cada medida o número de itens válidos e a cobertura do peso (`itens_validos_mes`, `cobertura_peso_mes`, `itens_validos_anual`, `cobertura_peso_anual`).

metricas_aberturas.parquet: desde 2019, as 4 aberturas de maior peso de cada subíndice e "Demais": `pai` (o subíndice), `componente` (`abertura_1` a `abertura_4` ou `demais`), `nome`, `frequencia`, `periodo`, `posicao`, `rotulo_periodo`, `data`, `variacao_anual` (nula em "Demais") e `contribuicao_no_pai`.

metricas_resumo.json: `ultimo_periodo`, `ultimo_rotulo`, `tipo_ultimo_release`, `frequencia_do_release`, `principais`, `expectativa`, `mensal_implicito` (nulo em release mensal), `difusao` e `destaques`.

validacao.json: data da checagem, último período e, para cada comparação, o desvio máximo e se passou. O dashboard não lê esse arquivo.

tabelas.json e graficos.json: o HTML das tabelas e as figuras do plotly, pelo nome do espaço no template.

## 6. As páginas do dashboard

No alto, as quatro abas (Resumo, Composição, Sazonalidade e Explorar) e, visível em todas, a faixa do release: à esquerda o último release, quando saiu e os números do INPC, do núcleo e do não núcleo; à direita o próximo release (os dias que faltam são contados pelo navegador, na hora em que a página abre) e, no dia da 1ª quinzena, a estimativa do número mensal que sai nele ("Estimativa para set/26: 0,42% no mês · 3,45% em 12 meses", a expectativa de mercado para o mesmo mês quando houver, com a mesma prioridade do card "Realizado x expectativa" ("Encuesta Citi espera 0,37% (núcleo 0,27%)", com a fonte inteira no tooltip) e o intervalo provável; o método e a cobertura de 50% em 56 meses fora da amostra ficam no tooltip), a hora da atualização e o selo de conferido com o INEGI. Tudo vem de `metricas_resumo.json` e do calendário.

Resumo:

- Cartões: INPC, Núcleo, Serviços e Mercadorias, o que o mercado cita no release. Cada um tem a taxa em 12 meses, a variação no período e a pílula com a mudança da taxa em 12 meses contra um mês antes ("▼ −0,14 pp vs 1ª quinz. ago"; no release mensal, "vs jul"). O não núcleo fica na faixa do release.
- Destaques: realizado x expectativa (a diferença é entre os dois números já arredondados, como na pílula, e o card diz de onde veio a expectativa), maiores contribuições (a que mais puxou para cima e a que mais puxou para baixo), maior desvio sazonal ("Acima do padrão: Jitomate +0,08 pp · Abaixo: Gasolina de bajo octanaje −0,02 pp") e difusão.
- INPC geral e Núcleo vs meta: a linha é mensal e, em release de quinzena, o ponto destacado é a última quinzena. Em todo gráfico com a meta, o eixo mostra a banda de 2% a 4% inteira, e a etiqueta "Meta 3%" fica na margem direita, na altura de 3%; se uma etiqueta de valor cair em cima dela, é a do valor que se afasta, mantendo a ordem dos valores. Nos gráficos com o ponto da quinzena, cada linha do tooltip diz o período do próprio ponto ("Núcleo (ago/26): 3,88%" e "Núcleo (1ª quinz. set/26): 3,79%").
- Os quatro gráficos de grupo mais usados, os mesmos da aba Composição.
- Último período vs padrão sazonal: barras dos sete principais com a mediana e o intervalo p25 a p75.
- Último release: para os sete principais, em hierarquia, a variação no período (em destaque) contra o padrão sazonal, e a taxa em 12 meses agora e um mês antes. Responde se o dado surpreendeu e se acelerou.
- Contribuições por abertura: as cinco que mais puxaram e as cinco que mais seguraram.

Composição:

- Treemap da contribuição do período, do INPC até os subíndices, em pp.
- Desvio em relação à mediana sazonal: as aberturas cujo desvio, vezes o peso efetivo, mais pesou, para cima e para baixo.
- Difusão, com a cobertura de cada medida no tooltip.
- Os 10 gráficos da seção de inflação do Informe Trimestral do Banxico: INPC, núcleo, mercadorias, serviços e não núcleo, com a variação em 12 meses à esquerda e a contribuição de cada filho à direita. No não núcleo, a direita é a mudança desde jul/2024.

Sazonalidade:

- Variação mensal dessazonalizada do INPC e do núcleo, nos últimos 36 meses.
- Momentum do núcleo: SAAR de 6 meses em destaque, SAAR de 3 meses e a variação em 12 meses.
- Perfil sazonal do INPC e de seis componentes: o ano corrente e os 3 anteriores contra a faixa p25-p75 e a mediana de 2010-2019. Só com azuis, é o tipo de traço que separa os anos.

Explorar: o mesmo par para as 16 categorias, na ordem da árvore, com o peso de cada uma na cesta 2024. Nos subíndices, os filhos são as 4 aberturas de maior peso e "Demais", com uma legenda por bloco. Cada gráfico só é desenhado quando chega perto da tela.

## 7. Validação

Roda depois do tratamento e antes de qualquer conta. Um nulo nunca passa: qualquer valor comparado que falte é falha, com o que faltou na mensagem.

1. Base completa: nos últimos 24 meses mais um ano (o lag da variação anual), os 16 componentes do catálogo têm índice e incidência em todos os períodos, nas duas frequências. A grade vem da coluna `posicao` e do catálogo, então um NaN, um componente que sumiu e um período ausente aparecem aqui.
2. Tabulado do mesmo período da base: um tabulado velho confere com o mês velho e não prova nada.
3. Último release contra o tabulado: variação, variação anual e incidência dos 16 componentes, no último mês (CA55) e na última quinzena (CA56). No release de exemplo, o desvio máximo foi de 0,005 pp, o arredondamento do tabulado.
4. Aditividade: nos últimos 24 meses, a incidência do núcleo mais a do não núcleo dá a variação do INPC. Desvio máximo de 0,0007 pp.

A tolerância é 0,01 pp, a menor diferença visível num número publicado com duas casas. Se uma checagem falha, o pipeline para com "Validação falhou" e o que faltou, e nenhuma etapa seguinte roda.

## 8. Limitações

- O calendário é anual. O `calendario_releases.csv` só tem 2026; depois de 23/12/2026 a ingestão avisa no terminal, o painel mostra "calendário 2027 ainda não carregado" e a base fica parada. Basta acrescentar uma linha por release quando o INEGI publicar o calendário de 2027, sem apagar as de 2026.
- A fonte DM Sans vem do Google Fonts. Sem internet, o navegador usa uma fonte do sistema; os números não mudam.
- A ponta da série dessazonalizada muda quando entra um mês novo (os números estão na metodologia).
- 16 genéricos só têm série a partir de 2024 (15 criados na cesta 2024 e um que começou em junho de 2024). Sem mediana de 2010-2019, ficam fora dos rankings de desvio; na incidência entram normalmente.
- As incidências vêm com 3 casas, então as contribuições deixam de fechar com o INPC em até 0,0045 pp. Onde falta incidência, a contribuição fica nula.
- A soma das incidências dos 292 genéricos difere do INPC na quarta casa (0,3293 contra 0,3291 na 1ª quinzena de setembro): é a diferença entre o meu peso efetivo e o cálculo interno do INEGI.
- O app "Índices de Precios" não é uma API documentada. Se o INEGI mudar os ids ou o exportador, a ingestão quebra; a validação impede que dado quebrado chegue ao painel, mas não conserta a ingestão.

## 9. Como acrescentar um gráfico

Digamos que eu queira a variação anual dos quatro componentes do nível 2.

1. Veja se a conta já existe. Aqui, `variacao_anual` já está em `metricas_componentes.parquet`. Conta nova vai em `metricas.py`, como coluna nova, nunca em `graficos.py`.
2. Escreva a função em `graficos.py`, na seção da aba certa, com a pergunta como docstring:

   ```python
   def decomp_nivel2_anual(componentes):
       """Qual dos quatro grandes grupos está puxando a inflação anual para cima?"""
       tracos = [go.Scatter(x=serie(componentes, c)["data"], y=serie(componentes, c)["variacao_anual"], mode="lines",
                            name=p.NOMES_EXIBICAO[c], meta={"componente": c}) for c in p.COMPONENTES_NIVEL_2]
       return com_meta(go.Figure(tracos).update_layout(yaxis_title="variação em 12 meses (%)"))
   ```

   Não ponha cor nem fonte: o `meta` basta para o template pintar cada componente.
3. Acrescente a figura ao dicionário `figuras`, no fim de `graficos.py`: `"decomp_nivel2_anual": decomp_nivel2_anual(componentes)`.
4. Abra o espaço no `template.html`, com o `data-card` igual à chave (`c6` é meia largura, `c12` a largura toda):

   ```html
   <div class="card c6" data-card="decomp_nivel2_anual">
     <h3>Grupos do nível 2</h3><p class="sub">Variação em 12 meses (%)</p>
   </div>
   ```

5. Rode `python pipeline/2_analise/graficos.py` e `python pipeline/3_dashboard/montagem.py`, abra o HTML e confira.

Para uma tabela, o caminho é o mesmo em `tabelas.py`, com `data-tipo="tabela"` no espaço do template.
