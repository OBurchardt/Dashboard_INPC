# Guia do projeto

Escrevi este guia para quem abre a pasta pela primeira vez, inclusive eu daqui a uns meses. Ele explica o que cada peça faz, de onde vem cada número e onde mexer quando algo precisar mudar. Os exemplos usam o último release que rodei, a 1ª quinzena de setembro de 2026, divulgada em 24/09/2026 às 06:00 da Cidade do México.

## 1. O que o projeto faz

O projeto baixa do INEGI as séries do INPC, o índice de preços ao consumidor do México, confere os números com o que o próprio INEGI publicou no release, faz as contas que um economista quer ver no dia e junta tudo num único arquivo HTML que abre sem internet.

A ideia é simples: às 06:00 da Cidade do México sai o dado, alguém roda `python run_pipeline.py` e, em poucos minutos, tem um painel com a inflação cheia e a do núcleo contra a meta do Banxico, de onde veio a alta, o que foi surpresa em relação ao normal daquela época do ano e se o ritmo está acelerando ou perdendo força.

Tudo vem de uma fonte só, o INEGI. Não uso nenhuma chave de API: o app "Índices de Precios", os xlsx de ponderadores e os tabulados do release são públicos. Se um dia alguma fonte exigir token, ele vai só no `.env` e nunca aparece no código nem em log.

No release de exemplo, o painel abre dizendo isto:

- INPC 0,33% na quinzena e 3,42% em 12 meses, 0,16 pp acima da quinzena anterior.
- Núcleo 0,17% na quinzena e 3,79% em 12 meses, 0,05 pp abaixo.
- Não núcleo 0,88% na quinzena e 2,17% em 12 meses, 0,86 pp acima.
- Mensal implícito de setembro: 0,42% no mês (entre 0,38% e 0,44%) e 3,45% em 12 meses.
- Maior contribuição: Jitomate, com +0,11 pp (o preço subiu 22,79% na quinzena).
- Maior surpresa vs padrão sazonal: Jitomate, +0,08 pp; para baixo, Gasolina de bajo octanaje, −0,02 pp.
- 62% da cesta com inflação anual acima de 3% (ago/26).

### Vocabulário: o que está no código e o que aparece na tela

O dashboard é lido por brasileiros, então a tela não usa os termos do INEGI. No código, nos nomes de colunas e neste guia, quando falo de metodologia, continuo com os termos originais, porque são os das fontes:

| no código e no INEGI | na tela |
|---|---|
| incidência | contribuição (em pp, para a variação do INPC cheio no período) |
| genérico | abertura |
| subíndice | grupo |
| norma sazonal | padrão sazonal (mediana de 2010 a 2019) |
| subyacente / no subyacente | Núcleo / Não núcleo (o nome oficial aparece num tooltip na primeira menção) |

Os nomes das aberturas vêm do INEGI e ficam em espanhol (Jitomate, Cebolla). Os nomes curtos dos componentes estão em `NOMES_EXIBICAO`, no `config/parametros.py`. Na tela, variações e contribuições têm sempre 2 casas decimais, como o IBGE publica.

## 2. Como rodar

Na primeira vez, numa máquina nova:

```
python -m venv .venv
.venv\Scripts\activate          (no Windows; no Linux e no Mac é source .venv/bin/activate)
pip install -r requirements.txt
python run_pipeline.py
```

As versões do `requirements.txt` estão fixadas e foram testadas com Python 3.12.4.

Tem uma única opção, no topo do `run_pipeline.py`:

```python
IMPORTAR_DO_ZERO = False
```

- `False` é o uso de todo dia. A ingestão olha o calendário e compara com a base. Se não saiu nada novo, ela nem vai à rede, imprime "Já atualizado" e as outras etapas refazem o dashboard em uns 8 a 12 segundos. Se saiu dado, ela rebaixa só os últimos 6 meses e sobrescreve esses períodos, o que também pega revisões do INEGI.
- `True` rebaixa todo o histórico, de 1969 até hoje, como se a base não existisse. Num clone limpo levou 305 segundos, dos quais 278 são só a ingestão. Nem precisa usar isso na primeira vez: com a base vazia, ou atrasada mais de 6 meses, a ingestão já decide sozinha baixar tudo.

No dia do release basta rodar a partir das 06:00 da Cidade do México. Antes desse horário a ingestão considera que o dado ainda não saiu, porque ela lê o calendário no fuso de lá, não no do computador. O HTML fica em `output/dashboard_inpc.html`.

Cada etapa também roda sozinha, por exemplo `python pipeline/2_analise/tabelas.py`, desde que as etapas anteriores já tenham gerado os arquivos de que ela precisa. Isso é útil para mexer num gráfico sem rebaixar nada.

Se a validação falhar, o pipeline para antes da montagem e o dashboard antigo continua lá. Prefiro mostrar o dashboard desatualizado a mostrar um número errado.

## 3. Mapa da pasta

```
run_pipeline.py              roda as oito etapas em ordem; IMPORTAR_DO_ZERO fica aqui
requirements.txt             versões fixas das bibliotecas
config/
  parametros.py              tudo o que é editável: caminhos, URLs, ids do INEGI, janelas, nomes da tela
  catalogo_series.csv        os 64 ids das séries de componentes e incidências, com nível e pai de cada um
  calendario_releases.csv    datas e horários de divulgação de 2026
pipeline/
  1_dados/
    ingestao.py              baixa do INEGI para data/raw
    tratamento.py            transforma o bruto em parquet longo em data/processed
    validacao.py             confere a base com o tabulado oficial; para tudo se falhar
    dessazonalizacao.py      tira a sazonalidade do índice mensal com STL
  2_analise/
    metricas.py              todas as contas: variações, incidências, norma, SAAR, difusão, resumo
    tabelas.py               as três tabelas em HTML
    graficos.py              as dez figuras em JSON do plotly
  3_dashboard/
    montagem.py              cabeçalho, cartões, destaques e o HTML final
    template.html            o visual inteiro: layout, cores, fontes e o JavaScript que desenha
docs/
  metodologia.md             fatos que descobri sobre os dados e as escolhas que fiz por causa deles
  guia_do_projeto.md         este guia
data/raw/                    o que veio do INEGI, quase como veio (gerada pelo pipeline)
data/processed/              as tabelas prontas para as contas e os JSON do dashboard (gerada)
output/                      dashboard_inpc.html (gerada)
```

As pastas `data/` e `output/` ficam fora do git: qualquer um recria rodando o pipeline.

## 4. Fluxo dos dados

```
INEGI
 ├─ app Índices de Precios (árvore + exportador CSV)
 ├─ xlsx de ponderadores 2018 e 2024
 └─ tabulados CA55 (mensal) e CA56 (quinzenal)
        │
        ▼  ingestao.py
data/raw/
  arvore_genericos_{mensal,quinzenal}.json
  componentes_{mensal,quinzenal}.csv
  incidencias_{mensal,quinzenal}.csv
  genericos_{mensal,quinzenal}.csv
  ponderadores_2018.xlsx, ponderadores_2024.xlsx
  tabulado_{mensal,quinzenal}.json
        │
        ▼  tratamento.py
data/processed/
  series.parquet, genericos.parquet, ponderadores.parquet, tabulado_oficial.parquet
        │
        ▼  validacao.py  ──►  validacao.json   (se falhar, para aqui)
        │
        ▼  dessazonalizacao.py  ──►  series_dessazonalizadas.parquet
        │
        ▼  metricas.py
  metricas_componentes.parquet, metricas_genericos.parquet,
  metricas_difusao.parquet, metricas_resumo.json
        │
        ├─►  tabelas.py   ──►  tabelas.json
        └─►  graficos.py  ──►  graficos.json
                 │
                 ▼  montagem.py (+ template.html + plotly.js + calendário)
output/dashboard_inpc.html
```

As etapas só conversam por arquivos. Nenhuma importa função de outra; todas importam só o `config/parametros.py`. É por isso que dá para rodar uma etapa sozinha.

## 5. Arquivo por arquivo

### run_pipeline.py

Lista as oito etapas e roda cada uma com `runpy.run_path`, passando `importar_do_zero` para dentro dela. Só a ingestão usa essa variável. No fim imprime o tempo total. Não tem mais nada ali de propósito: a ordem das etapas é a documentação do fluxo.

### config/parametros.py

Um arquivo de constantes, dividido em seções.

- **Caminhos.** As pastas; importar o arquivo já cria as que faltam.
- **Tempo.** O fuso da Cidade do México e a janela de 6 meses da atualização.
- **Rede.** 3 tentativas, 120 s de limite e lotes de 120 ids por pedido ao exportador.
- **Fontes.** As URLs.
- **Estruturas.** Os ids internos do app que achei navegando nele. `112001700010` é o índice mensal dos 16 componentes, `112001600020` o quinzenal, `112001800030` e `112001800020` as incidências. As árvores `112001700030` e `112001600030` são as únicas que descem até os 292 genéricos.
- **Componentes e nomes.** Quais são os três principais, quais são os quatro do nível 2 e o nome de cada um na tela, em português (Núcleo, Mercadorias, Energia e tarifas...).
- **Janelas.** Dessazonalização desde 2000, norma de 2010 a 2019, gráficos desde 2019, início da cesta 2024, 24 meses de genéricos no dashboard e tolerância de 0,01 pp na validação.

### pipeline/1_dados/ingestao.py

- `pedir`: faz o GET ou POST com até 3 tentativas. É a única tolerância a erro do projeto, porque o servidor do INEGI derruba conexão de vez em quando.
- `periodo_padrao`: converte o rótulo do INEGI para o meu formato ("2026-08" no mensal e "2026-09-Q1" no quinzenal).
- `mes_do_periodo`: número de meses desde o ano zero, para medir o atraso da base.
- `filhos_do_no`, `varrer_arvore`, `baixar_arvore`: percorrem a árvore do app nó por nó (o serviço `ObtieneNodosV2` devolve HTML) e guardam cada nó com id, nome, id da série, pai, nível e se é genérico. Se vierem menos de 292 genéricos, varro de novo uma vez; se continuar faltando, paro com uma mensagem.
- `ler_csv_exportador`, `exportar`: pedem ao exportador do app as séries de uma estrutura entre dois anos. O CSV vem em Windows-1252 e tem um cabeçalho de texto solto; os dados começam na linha "Fecha".
- `conjuntos_de_series`: as seis tabelas que mantenho (componentes, incidências e genéricos, cada uma em mensal e quinzenal). Os ids dos componentes saem do catálogo e os dos genéricos, da árvore.
- `salvar_tabela`: grava o CSV. Na atualização, os períodos que chegaram substituem os mesmos períodos da base.
- `baixar_ponderadores`, `baixar_tabulados`: os dois xlsx e os dois tabulados do release. No tabulado acrescento o campo "periodo" no meu formato.
- `ultimo_divulgado`: lê o calendário e diz qual o último período já publicado. Cuidado: o release "mensal" traz também a 2ª quinzena do mesmo mês.
- `ultimo_na_base`: o último período presente em todas as tabelas. Fico com o menor, porque basta uma atrasada para a base estar atrasada.
- `baixar_historico_completo`, `atualizar`, `avisar_se_o_calendario_acabou`: os dois modos e o aviso de que o calendário acabou.

### pipeline/1_dados/tratamento.py

- `normalizar`: tira acentos, maiúsculas e pontuação dos nomes, porque o INEGI escreve o mesmo nome de jeitos diferentes em cada arquivo.
- `rotulos_do_periodo`: os três rótulos de tela. Para "2026-09-Q1" são "1ª quinz. set/26", "1ª q. set" e "set/26".
- `data_do_periodo`: a 1ª quinzena vai para o dia 1 e a 2ª para o dia 16, para caberem no eixo do mensal.
- `ler_tabela_raw`: abre um CSV de `data/raw` e passa para o formato longo. O "N/E" antes do começo de uma série é descartado; um buraco no meio fica nulo.
- `ler_arvore`: dos nós da árvore, só os genéricos, com o código de 3 dígitos separado do nome ("205 Jitomate" vira código "205" e nome "Jitomate").
- `montar_series`: componentes e incidências juntos, com nível e pai tirados do catálogo.
- `ler_planilha_ponderadores`, `montar_ponderadores`: leem a planilha do INEGI, onde cada genérico tem um X na coluna do seu subíndice. O código de cada genérico vem do nome casado com a árvore.
- `montar_genericos`: o índice de cada genérico em cada período, com o subíndice oficial da cesta 2024.
- `montar_tabulado_oficial`: o tabulado do release numa tabela simples, que a validação só compara.

### pipeline/1_dados/validacao.py

São duas checagens (a seção 8 explica as duas). A validação recalcula as variações sozinha, sem usar a etapa de métricas, para ser um teste independente.

### pipeline/1_dados/dessazonalizacao.py

`dessazonalizar` aplica o STL do statsmodels no log do índice mensal, com ciclo de 12 meses e a opção robusta a outliers, de 2000 para cá. O índice sem sazonalidade é `exp(log(índice) − componente sazonal)`. O quinzenal não é dessazonalizado; para ele a leitura sazonal é a comparação com a norma.

### pipeline/2_analise/metricas.py

As fórmulas estão todas aqui.

**Variações** (`acrescentar_variacoes`)

```
variação no período = (Iₜ / Iₜ₋₁ − 1) × 100
variação anual      = (Iₜ / Iₜ₋ₙ − 1) × 100,   n = 12 no mensal, 24 no quinzenal
```

**Norma sazonal** (`acrescentar_norma`). Para cada série e cada posição no ano ("09" no mensal, "09-Q1" no quinzenal), calculo a mediana, o p25 e o p75 da variação no período entre 2010 e 2019. O desvio é a variação de agora menos a mediana. Uso a mediana e não a média porque a janela tem choques, como a liberalização da gasolina em janeiro de 2017. No exemplo, o INPC subiu 0,33% na 1ª quinzena de setembro, e a norma dessa quinzena é 0,32% (p25 0,23% e p75 0,34%): um dado dentro do normal.

**Incidência dos componentes.** Essa eu não calculo: é a série de incidência que o INEGI publica. A dos genéricos eu calculo, com o peso efetivo.

**Peso efetivo do genérico** (`peso_efetivo_do_generico`). Na cesta 2024, o INPC é a média ponderada dos genéricos, com cada índice dividido pelo seu fator de encadeamento (o índice da 2ª quinzena de julho de 2024 dividido por 100):

```
relativo do genérico  = índice do genérico / fator de encadeamento
relativo do INPC      = INPC / (INPC da 2Q jul/2024 / 100)
peso efetivo          = ponderador × relativo do genérico (t−1) / relativo do INPC (t−1) / 100
incidência            = peso efetivo × variação no período
```

Com o jitomate na 1ª quinzena de setembro:

- ponderador 0,7892 e fator 2,4055;
- índice na 2ª quinzena de agosto: 150,821, então relativo = 62,70;
- INPC na 2ª quinzena de agosto: 145,531; na 2Q jul/2024: 136,095; então relativo do INPC = 106,93;
- peso efetivo = 0,7892 × 62,70 / 106,93 / 100 = 0,00463;
- variação na quinzena = 22,79%, então incidência = 0,00463 × 22,79 = 0,105 pp, que é exatamente o que o INEGI publica.

O peso efetivo não é o peso da planilha: um item que subiu mais que o INPC desde julho de 2024 passa a pesar mais. Antes da cesta 2024 os pesos eram outros, então não calculo incidência de genérico antes dela.

**Contribuição da surpresa**

```
contribuição da surpresa = peso efetivo × desvio da norma
```

O jitomate teve 22,79% contra uma norma de 5,46%, então o desvio é de 17,33 pontos e a contribuição da surpresa é 0,00463 × 17,33 = 0,080 pp. Ordenar pelo desvio em % puro poria sempre frutas e verduras no topo, porque oscilam muito; multiplicado pelo peso, ele vira pontos do INPC.

**Contribuição para a inflação anual** (`acrescentar_contribuicao_anual`). Somo as incidências dos últimos 12 meses (ou 24 quinzenas) de cada componente. Essa soma é aproximada, porque cada incidência usa o peso relativo do seu mês e fica faltando o efeito composto. Para fechar exatamente, reescalo as partes de cada nível:

```
contribuição anual = soma das incidências em 12 meses × (inflação anual do INPC / soma do nível)
```

Em agosto de 2026: Mercancías 1,28 pp, Servicios 1,71 pp, Energéticos e tarifas 0,42 pp e Agropecuarios −0,15 pp, somando 3,26%, que é o INPC em 12 meses.

**Ritmo dessazonalizado** (`acrescentar_ritmo_dessazonalizado`). Sobre o índice sem sazonalidade:

```
variação mensal SA = (SAₜ / SAₜ₋₁ − 1) × 100
SAAR de m meses    = ((SAₜ / SAₜ₋ₘ)^(12/m) − 1) × 100,   m = 3 ou 6
```

A subyacente de agosto tem SAAR de 3 meses de 4,03% e de 6 meses de 3,90%, contra 3,88% em 12 meses. O ritmo recente está um pouco acima da anual.

**Difusão** (`serie_difusao`). Mês a mês, a parte do peso da cesta que está em genéricos com alta no mês, com alta anual acima de 3% (a meta) e acima de 4% (o teto da banda). Cada mês usa os pesos da cesta que valia na época, 2018 ou 2024, e reparto o peso só entre os genéricos que têm dado. Em agosto de 2026: 68% da cesta subiu no mês, 62% está acima de 3% em 12 meses e 37% acima de 4%.

**Mensal implícito** (`mensal_implicito`). No dia da 1ª quinzena ainda não existe o mês. Como o índice mensal é a média das duas quinzenas, metade da média já está publicada, e a outra metade parte do mesmo nível. O único incerto é quanto a 2ª quinzena sobe sobre a 1ª, e para isso uso a norma:

```
índice do mês = (1ª quinzena + 1ª quinzena × (1 + norma da 2ª quinzena)) / 2
```

Em setembro: a 1ª quinzena é 146,010; a mediana da 2ª quinzena de setembro em 2010-2019 é de alta de 0,083%, o que dá 146,132 para a 2ª; a média das duas é 146,071; contra agosto (145,462), isso dá 0,42% no mês e 3,45% em 12 meses. Com o p25 e o p75 da norma o intervalo fica entre 0,38% e 0,44%.

**Resumo** (`numeros_principais`, `destaques`, `registros`, `arredondar`). O `metricas_resumo.json` guarda o que vai no topo do painel: o último período, se o release foi de 1ª quinzena ou mensal, os números dos três principais, o mensal implícito, a difusão e os cinco genéricos de cada lista. Guardo 6 casas e deixo o arredondamento para a tela; arredondar duas vezes já me fez errar o último dígito.

Uma decisão importante acontece aqui e só aqui: se o último quinzenal termina em "Q1", o release é de 1ª quinzena e o dado principal é quinzenal; caso contrário, o dado principal é o mês. As etapas seguintes só leem `frequencia_do_release`.

### pipeline/2_analise/tabelas.py

- `celula_numero`: formata com vírgula decimal e 2 casas, usa o sinal de menos tipográfico e marca a célula como positiva ou negativa. O que arredonda para zero sai "0,00", sem sinal e sem cor.
- `celula_texto`, `tabela_html`, `grupo`: o resto do HTML das tabelas.
- `main_ultimos_periodos`, `main_top_incidencias`, `decomp_desvios`: as três tabelas. Não fazem conta, só escolhem e formatam. Os cabeçalhos já saem no vocabulário da tela (Abertura, Grupo, Contribuição, Padrão sazonal).

### pipeline/2_analise/graficos.py

Uma função por gráfico, com o mesmo nome do espaço que ele ocupa no template. As figuras saem sem estilo nenhum; cada traço leva em `meta` o componente a que se refere, e o template decide a cor por ele. As funções de apoio são `serie`, `linha` e `com_meta` (a última desenha a meta de 3% e a banda de 2% a 4%).

### pipeline/3_dashboard/montagem.py

- `numero`: o formatador dos cartões; um valor que arredonda para zero sai "0,00", sem sinal.
- `releases`, `proximo_release`: leem o calendário. Depois do último release do arquivo, o cabeçalho diz "Próximo release: calendário 2027 ainda não carregado".
- `kpi`: um cartão, com a seta decidida pelo valor já arredondado. Se a mudança aparece como 0,00, a seta é "=" e o cartão fica neutro.
- `mensal_implicito`, `cabecalho`: o texto da faixa do release e dos cartões. Cada cartão leva o nome do componente, para o template saber onde pôr o tooltip do nome oficial.
- `destaques`, `nome`: as quatro frases do topo, só com fatos do resumo, em 2 casas.
- No fim, o JSON de tudo e o plotly.js são colados no template, e o arquivo é gravado em `output/`.

### pipeline/3_dashboard/template.html

HTML, CSS e JavaScript num arquivo só. As cores, fontes e raios estão em variáveis no `:root`, com a paleta tirada do site do BTG Pactual (sem logo nem nome do banco): `--azul-btg` #10408D como cor primária, `--azul-claro` #B0D2FF e `--azul-claro-2` #E8F1FF nos blocos e fundos, cantos de 4px. O JavaScript lê `window.DADOS`, preenche a faixa do release e os cartões, aplica o estilo a cada figura conforme o `meta` e ajusta as tabelas. Nas tabelas, só uma coluna leva a cor do sinal (`COLUNA_COLORIDA`) e as colunas de contribuição ganham uma barrinha.

## 6. Dicionário de dados

### data/raw

| arquivo | o que tem |
|---|---|
| `componentes_{freq}.csv` | uma linha por período, uma coluna por id de série; índices dos 16 componentes. Mensal desde 1970-01, quinzenal desde 1988-01-Q1 |
| `incidencias_{freq}.csv` | mesmo formato; incidências dos 16 componentes, em pp. Desde 2002 |
| `genericos_{freq}.csv` | mesmo formato; índices dos 292 genéricos. Mensal desde 1970, quinzenal desde 1995 |
| `arvore_genericos_{freq}.json` | os 463 nós da árvore: `id_no`, `nome`, `id_serie`, `generico`, `id_pai`, `nivel` |
| `ponderadores_2018.xlsx`, `ponderadores_2024.xlsx` | as planilhas oficiais, sem alteração |
| `tabulado_{freq}.json` | a resposta do tabulado do release (`Datos`, `Encab`, `InfoTab`, `PeriodoDisponible`) mais o meu `periodo` |

Os valores ficam como texto, com "N/E" onde o INEGI não publica, e os CSVs abrem direto no Excel.

### data/processed

**series.parquet**: componentes e incidências, uma linha por série e período.

| coluna | significado |
|---|---|
| `id_serie` | id do INEGI |
| `tipo` | "indice" ou "incidencia" |
| `componente`, `nivel`, `pai` | nome interno, nível na hierarquia (0 a 3) e componente de cima |
| `frequencia` | "mensal" ou "quinzenal" |
| `periodo` | "2026-08" ou "2026-09-Q1" |
| `rotulo_periodo`, `rotulo_curto`, `rotulo_mes` | "1ª quinz. set/26", "1ª q. set", "set/26" |
| `data` | dia 1, ou dia 16 na 2ª quinzena |
| `valor` | índice (base 2Q jul/2018 = 100) ou incidência em pp |

**genericos.parquet**: `codigo_generico`, `nome_generico`, `subindice`, `componente_nivel2`, `componente_nivel1`, `frequencia`, `periodo`, os três rótulos, `data` e `indice`.

**ponderadores.parquet**: `cesta` ("2018" ou "2024"), `codigo_generico` (nulo nos 28 genéricos da cesta 2018 que saíram), `nome_generico`, `ponderador` (em %, soma 100 em cada cesta), `subindice`, `componente_nivel2`, `componente_nivel1`, `fator_encadeamento` (só na 2024), `vigencia_inicio`, `vigencia_fim`.

**tabulado_oficial.parquet**: `frequencia`, `periodo`, `componente`, `variacao`, `variacao_anual`, `incidencia`. São 16 linhas por frequência, só do último release.

**series_dessazonalizadas.parquet**: `componente`, `periodo`, `data`, `indice_sa`. Só o mensal, desde 2000.

**metricas_componentes.parquet**: as colunas de identificação de `series` mais `indice`, `variacao_periodo`, `variacao_anual`, `incidencia_periodo`, `contribuicao_anual`, `norma_mediana`, `norma_p25`, `norma_p75`, `desvio_norma`, `variacao_sa_mensal`, `saar_3m` e `saar_6m` (as três últimas só no mensal). Variações em %, incidências e contribuições em pp.

**metricas_genericos.parquet**: os últimos 24 meses de cada genérico, com `variacao_periodo`, `variacao_anual`, `norma_mediana`, `desvio_norma`, `incidencia_periodo` e `contribuicao_surpresa`.

**metricas_difusao.parquet**: mensal, desde 2019: `pct_genericos_em_alta` (por contagem), `pct_cesta_em_alta`, `pct_cesta_anual_acima_3` e `pct_cesta_anual_acima_4` (por peso).

**metricas_resumo.json**: `ultimo_periodo`, `ultimo_rotulo`, `tipo_ultimo_release`, `frequencia_do_release`, `principais`, `mensal_implicito` (nulo em release mensal), `difusao` e `destaques`.

**validacao.json**: data da checagem, último período e, para cada checagem, desvio máximo e ok. O dashboard não lê esse arquivo; ele fica para consulta.

**tabelas.json** e **graficos.json**: o HTML das tabelas e as figuras do plotly, por nome de espaço.

## 7. As páginas do dashboard

Toda figura tem uma pergunta, que também é a docstring da função em `graficos.py`.

### Barra de navegação e faixa do release

No alto, uma barra branca com "INPC México · Monitor do release" à esquerda e as quatro abas à direita. Logo abaixo, e visível em todas as abas, a faixa do release em dois blocos:

- à esquerda, em azul: "Último release · 1ª quinzena set/26 · divulgado 24/09 06:00 CDMX", "INPC 3,42% em 12 meses" e "Núcleo 3,79% · Não núcleo 2,17% · variação na quinzena 0,33%";
- à direita, em azul claro: o próximo release (08/10/2026 06:00, em 12 dias), a hora da atualização e o selo "Conferido com o INEGI · 1ª quinz. set/26".

Os dados vêm de `metricas_resumo.json` e do calendário.

### Resumo

- **Cartões.** INPC, Núcleo e Não núcleo no período e em 12 meses, com a seta da mudança da anual, mais o cartão do mensal implícito no dia da 1ª quinzena. Fonte: `metricas_resumo.json`.
- **Destaques.** As quatro frases da seção 1. Fonte: `metricas_resumo.json`.
- **INPC geral vs meta** e **Núcleo vs meta.** A inflação cheia está dentro da meta, e para onde aponta a última quinzena? O núcleo está convergindo para 3%? A linha é mensal e o ponto é a última quinzena (3,42% no INPC e 3,79% no núcleo). Fonte: `metricas_componentes`.
- **Contribuições para a inflação em 12 meses.** De onde vem a inflação anual? Barras empilhadas dos quatro componentes do nível 2 nos últimos 24 meses, e a linha do INPC. Fonte: `contribuicao_anual`.
- **Último período vs padrão sazonal.** O último dado veio acima ou abaixo do que costuma acontecer nessa época do ano? Barras dos sete principais, com a mediana e o intervalo p25 a p75. No exemplo, o não núcleo subiu 0,88% e o INPC 0,33% contra um padrão de 0,32%. Fonte: `metricas_componentes`.
- **Últimos períodos.** Tabela com as três últimas quinzenas (ou meses) e a variação em 12 meses. Fonte: `metricas_componentes`.
- **Contribuições por abertura.** As cinco que mais puxaram e as cinco que mais seguraram, com o grupo embaixo do nome: Jitomate +0,11 pp, Primaria +0,03 e Cebolla +0,03 de um lado; Servicios profesionales −0,04 e Papa y otros tubérculos −0,03 do outro. O subtítulo define contribuição em uma linha. Fonte: `destaques` do resumo.

### Composição

- **Decomposição da variação do período.** Do INPC até os grupos, quanto cada parte puxou? Treemap com a contribuição publicada pelo INEGI. No exemplo: Núcleo +0,13 pp e Não núcleo +0,20 pp, e dentro deste, Frutas e verduras +0,14 pp. Fonte: `incidencia_periodo` dos componentes.
- **Surpresas vs padrão sazonal.** Quais aberturas se mexeram fora do normal, com peso? Colunas: Abertura, Grupo, Variação, Padrão sazonal e Contribuição da surpresa, esta a única com cor e barrinha, em duas seções ("Acima do padrão" e "Abaixo do padrão"). Para cima, Jitomate +0,08, Pollo +0,02 e Gas doméstico LP +0,02; para baixo, Gasolina de bajo octanaje −0,02, Automóviles −0,02 e Papa y otros tubérculos −0,02. Fonte: `destaques` do resumo.
- **Serviços vs mercadorias.** Serviços, que são mais inerciais, estão se descolando de mercadorias? Fonte: `variacao_anual`.

### Tendência

- **Variação mensal dessazonalizada.** Sem sazonalidade, a inflação de cada mês está acelerando? Barras de 36 meses do INPC e do núcleo. Fonte: `variacao_sa_mensal`.
- **Momentum do núcleo.** O ritmo recente está acima ou abaixo da anual? SAAR de 3 e 6 meses contra a variação em 12 meses. Fonte: `saar_3m`, `saar_6m`.
- **Perfil sazonal do INPC.** Este ano está subindo mais ou menos do que é normal em cada mês? A faixa de 2010-2019 e a linha de 2026 até agosto. Fonte: padrão sazonal (`norma_*`) e `variacao_periodo` mensal.
- **Difusão.** A inflação está espalhada ou concentrada? Parte da cesta com alta no mês e com alta acima de 4% em 12 meses. Fonte: `metricas_difusao`.

### Fontes externas

Por enquanto vazia. É o lugar reservado para surpresa contra o consenso e projeções do Banxico.

## 8. Validação

A validação roda depois do tratamento e antes de qualquer conta, e são duas checagens.

1. **Último release contra o tabulado oficial.** Recalculo a variação, a variação anual e a incidência dos 16 componentes no último mês e na última quinzena, e comparo com o tabulado CA55 (mensal) e CA56 (quinzenal) que o INEGI publica no release. Se um dado faltar, vier trocado ou for de outro período, aparece aqui. No release de exemplo, o desvio máximo foi de 0,005 pp, que é só o arredondamento do tabulado.
2. **Aditividade das incidências.** Nos últimos 24 meses, a incidência da subyacente mais a da no subyacente tem de dar a variação do INPC geral. Isso só acontece se índices e incidências forem coerentes entre si. Desvio máximo: 0,0007 pp.

A tolerância é 0,01 pp, a menor diferença visível num número publicado com duas casas. Se uma checagem passar disso, o pipeline para com a mensagem "Validação falhou" e a montagem não roda. O resultado fica em `data/processed/validacao.json`.

Na auditoria que fiz ao fechar o projeto conferi também, à mão, os números do painel contra o site do INEGI: INPC 3,42% e subyacente 3,79% na 1ª quinzena de setembro, e as incidências de jitomate (0,105), primaria (0,027), cebolla (0,027), gas LP (0,026) e pollo (0,025). Tudo bateu.

## 9. Limitações

- **O calendário é anual.** O `calendario_releases.csv` só tem 2026. Depois de 23/12/2026, a ingestão avisa no terminal e o painel mostra "calendário 2027 ainda não carregado". Sem o calendário novo, a base fica congelada dizendo que está em dia. Para resolver, basta acrescentar uma linha por release, no mesmo formato, quando o INEGI publicar o calendário de 2027.
- **A fonte precisa de internet.** O painel abre offline, mas a fonte Inter vem do Google Fonts. Sem conexão, o navegador usa uma fonte do sistema; os números continuam os mesmos, só muda a aparência.
- **O fim da série dessazonalizada muda.** O STL é recalculado a cada rodada, e os últimos meses são os menos firmes, porque o filtro não tem dado do lado de lá. O SAAR de 3 meses de hoje pode mudar um pouco quando entrarem os próximos meses; o gráfico de momentum avisa isso numa nota.
- **Genéricos sem histórico.** 16 genéricos só têm série a partir de 2024: 15 foram criados na cesta 2024 (a lista está na `metodologia.md`) e um começou em junho de 2024. Eles não têm norma de 2010-2019, então ficam sem desvio e sem contribuição da surpresa, e não entram nos rankings de surpresa. Na incidência eles entram normalmente.
- **A contribuição anual é uma aproximação.** A soma das incidências de 12 meses não fecha exatamente com a inflação anual, e eu reescalo para fechar. O tamanho relativo de cada parte está certo; o valor exato de cada uma depende dessa reescala.
- **A soma das incidências dos genéricos difere um pouco do INPC.** Em agosto, a soma dos 292 deu 0,2021 contra 0,2018 de variação do INPC; na 1ª quinzena de setembro, 0,3293 contra 0,3291. É a diferença entre o meu peso efetivo e o cálculo interno do INEGI, e fica na quarta casa.
- **Dependo do site do INEGI.** O app "Índices de Precios" não é uma API documentada: os ids das estruturas e o formato do exportador foram descobertos navegando nele. Se o INEGI mudar o app, a ingestão quebra e é preciso redescobrir esses ids. A validação garante que um dado quebrado não chegue ao painel, mas não conserta a ingestão.
- **As incidências de agosto de 2018 não existem.** O INEGI não publicou, e o buraco fica nulo; afeta só a contribuição anual de 2018 e 2019, fora da janela dos gráficos.

## 10. Como acrescentar um gráfico

Como exemplo, digamos que eu queira um gráfico da variação anual dos quatro componentes do nível 2.

1. **Veja se a conta já existe.** Aqui, `variacao_anual` já está em `metricas_componentes.parquet`. Se o gráfico precisar de uma conta nova, ela vai em `metricas.py`, como coluna nova nessa tabela, e nunca dentro de `graficos.py`.

2. **Escreva a função em `graficos.py`**, na seção da página certa, com a pergunta como docstring:

   ```python
   def decomp_nivel2_anual(componentes, nomes, resumo):
       """Qual dos quatro grandes grupos está puxando a inflação anual para cima?"""
       figura = go.Figure([linha(serie(componentes, c), "variacao_anual", c, nomes[c]) for c in p.COMPONENTES_NIVEL_2])
       return com_meta(figura.update_layout(yaxis_title="variação em 12 meses (%)"))
   ```

   Não ponha cor nem fonte; o `meta` que a `linha` já coloca basta para o template pintar cada componente. Os nomes das séries saem de `NOMES_EXIBICAO`, e qualquer texto novo segue o vocabulário da tela (seção 1).

3. **Inclua a função na lista `slots`** no fim de `graficos.py`.

4. **Abra um espaço no `template.html`**, na seção da página:

   ```html
   <div class="card c6" data-card="decomp_nivel2_anual">
     <h3>Grupos do nível 2</h3><p class="sub">Variação em 12 meses (%)</p>
   </div>
   ```

   O `data-card` tem de ser igual ao nome da função. `c6` ocupa meia largura e `c12` a largura toda.

5. **Rode só o que mudou**: `python pipeline/2_analise/graficos.py` e depois `python pipeline/3_dashboard/montagem.py`. Abra o HTML e confira.

Para uma tabela, o caminho é o mesmo em `tabelas.py`, com `data-tipo="tabela"` no espaço do template. Se o gráfico precisar de um número editável, como uma janela de meses usada em mais de um lugar, ele vai em `config/parametros.py`.
