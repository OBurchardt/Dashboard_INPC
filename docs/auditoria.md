# Auditoria final

Auditoria feita em 27/09/2026 sobre o commit c6b781e, com a base do release da 1ª quinzena de setembro de 2026
(mensal até ago/26). Cada linha da tabela diz o que conferi, o valor no pipeline, a referência, de onde ela veio e a
diferença. As conferências usaram código escrito à parte, fora do repositório, que recalcula tudo a partir de
`data/raw`, das planilhas oficiais e das fontes externas, sem importar nenhuma função do pipeline. Os scripts foram
apagados no fim, como pede o CLAUDE.md.

## Resumo

1. Os 16 componentes batem com os tabulados CA55 e CA56 do INEGI na casa publicada: 48 casos (ago/26, 1ª quinz. set/26 e 2ª quinz. ago/26), variação, 12 meses e incidência, diferença zero.
2. Os comunicados de jul/26, ago/26 e 1ª quinz. set/26 batem inteiros: quadro 1 (16 componentes, 4 medidas, incluindo a incidência anual) e quadro 2 (os 60 genéricos listados).
3. O histórico inteiro dos 7 componentes principais é idêntico ao da API do BIE (canal independente do app), nas duas frequências, desde 1970 e 1988. Os 9 subíndices foram conferidos em 12 períodos dos comunicados e por consistência interna em todo o histórico.
4. Todas as identidades fecham: mensal = média das quinzenas, incidências somam o pai e o INPC, contribuição em 12 meses, contribuição no pai e no grupo (inclusive na troca de cesta de 2024), aberturas + "Demais".
5. STL, SAAR, medianas sazonais, desvio sazonal ponderado, difusão e a estimativa do mês, refeitos com código próprio, dão os mesmos números (diferença abaixo de 1e-6).
6. Os 15 números do Informe Trimestral abr-jun/2026 do Banxico batem na 2ª casa.
7. As 24 datas do calendário de 2026 batem com o calendário oficial do INEGI, todas às 06:00.
8. No HTML: faixa, cartões, destaques e tabelas conferem; os 21 gráficos de contribuição somam a linha; etiquetas da ponta são o último valor; sem erro de JavaScript e sem rolagem horizontal a 1440 e 390 px, offline.
9. Clone limpo, ambiente novo, sem variável de ambiente: `pip install` e `python run_pipeline.py` rodam do zero (292 s) e no incremental (12 s), com resultado idêntico ao da base atual, byte a byte.
10. Achei 2 bugs que mudam número na tela (ambos fora do estado atual do painel) e 8 menores, listados no fim.

## Checagens

### Números oficiais

| o quê | pipeline | referência | fonte | diferença | ok |
|---|---|---|---|---|---|
| 16 componentes, ago/26: variação, 12 meses, incidência | 48 valores | tabulado CA55_2018A, esquema 4 | API de tabulados do INEGI, baixada em 27/09 | 0 em todos (após arredondar à casa publicada) | ok |
| 16 componentes, 1ª quinz. set/26 | 48 valores | CA56_2018A, esquema 4 | idem | 0 | ok |
| 16 componentes, 2ª quinz. ago/26 | 48 valores | CA56_2018A, esquema 1 | idem | 0 | ok |
| INPC 12 meses jul/26, ago/26, 1ª quinz. set/26 | 3,12 / 3,26 / 3,42 | 3,12 / 3,26 / 3,42 | boletins 2q2026_08, 2q2026_09, 1q2026_09 | 0 | ok |
| Núcleo 12 meses ago/26 e 1ª quinz. set/26 | 3,88 / 3,79 | 3,88 / 3,79 | idem | 0 | ok |
| INPC na quinzena | 0,33 | 0,33 | boletim 1q2026_09 | 0 | ok |
| Quadro 1 dos 3 boletins: 16 componentes x (variação, 12 meses, incidência) | 144 valores | 144 valores | boletins | 0 | ok |
| Incidência anual (quadro 1) contra a contribuição em 12 meses do pipeline | 48 valores | 48 valores | boletins | máx 0,0005 pp (o INEGI publica com 3 casas) | ok |
| Colunas 2024 e 2025 dos quadros 1 (jul, ago e 1ª quinz. set de 2024 e 2025) | 96 valores | 96 valores | boletins | 0 | ok |
| Quadro 2 (genéricos com maior incidência), 3 boletins | 60 genéricos recalculados | 60 genéricos | boletins | 0 em variação e incidência | ok |
| 5 maiores e 5 menores do último release | Jitomate 0,105; Primaria 0,027; Cebolla 0,027; Gas LP 0,026; Pollo 0,025; Servicios profesionales −0,043; Papa −0,025; Tequila −0,008; Productos para el cabello −0,007; Automóviles −0,006 | os mesmos, na mesma ordem | boletim 1q2026_09, quadro 2 | 0 | ok |
| Histórico do índice, 7 componentes, mensal | 536 a 680 períodos por série, 1970-01 a 2026-08 | API do BIE (ids 910392 a 910398) | INEGI, BIE-BISE | máx 1e-12; nenhuma acima de 0,001 | ok |
| Histórico do índice, 7 componentes, quinzenal | 929 períodos por série, 1988-01-Q1 a 2026-09-Q1 | API do BIE (910420 a 910426) | INEGI, BIE-BISE | máx 1e-12 | ok |
| Histórico dos 9 subíndices | 12 períodos (jul, ago, 1ª quinz. set de 2024, 2025, 2026 e 2ª quinz. ago/26) | boletins e tabulados | INEGI | 0 | ok, parcial |
| Histórico dos 9 subíndices, todos os períodos, contra fonte externa | | | nem o BIE nem o SIE do Banxico expõem essas séries com id que eu tenha achado | | não verificado |
| Banxico: núcleo 3,93 = serviços 2,22 + mercadorias 1,71 (1ª quinz. ago/26) | 3,9346 = 2,2221 + 1,7126 | 3,93 = 2,22 + 1,71 | Informe Trimestral abr-jun/2026, PDF de 26/08/2026, gráficas da seção de inflação | 0 na 2ª casa | ok |
| Banxico: serviços 4,34 = habitação 1,63 + educação 0,39 + outros 2,32 | 4,3415 = 1,6271 + 0,3896 + 2,3247 | idem | idem | 0 | ok |
| Banxico: mercadorias 3,51 = alimentos 2,21 + não alimentícias 1,30 | 3,5081 = 2,2130 + 1,2951 | idem | idem | 0 | ok |
| Banxico: não núcleo 0,96; mudança desde jul/24 −9,40 | 0,9634; −9,3985 | 0,96; −9,40 | idem | 0 | ok |
| Banxico: frutas e verduras −4,46, energia −2,99, pecuários −2,90, tarifas +0,94 | −4,4576; −2,9859; −2,8991; +0,9441 | idem | idem | 0 | ok |
| Calendário: 24 releases de 2026, data e hora | `config/calendario_releases.csv` | calendário de difusão 2026 (cal_2026.pdf) e a data de cada boletim | INEGI | 24 de 24 iguais, todas às 06:00 | ok |
| Próximo release e "em N dias" no HTML (montado em 27/09 00:42) | 08/10/2026 06:00, 11 dias | 08/10/2026 06:00; 11 dias | calendário do INEGI e a API da sala de imprensa | 0 | ok (ver bug B2) |

### Identidades e cálculos

| o quê | pipeline | referência | fonte | diferença | ok |
|---|---|---|---|---|---|
| Estrutura: 16 componentes, ordem e hierarquia | catálogo | tabulado CA55 (ordem e identação) | INEGI | igual | ok |
| Genéricos na cesta 2024 e 2018 | 292 e 299 | 292 e 299 com X na planilha | xlsx de ponderadores | 0 | ok |
| Pesos somam 100 | 100,000000 nas duas cestas | 100 | planilhas | 0 | ok |
| Cada genérico com um subíndice só; peso, fator e subíndice iguais à planilha | 292 | 292 | planilha 2024 | 0 | ok |
| Fator de encadeamento do INPC | 1,360952 | INPC 2ª quinz. jul/24 / 100 = 1,360950 | planilha e base | 0,000002 | ok |
| Fatores dos 292 genéricos | planilha | índice de cada um na 2ª quinz. jul/24 / 100 | base | máx 0,000005 | ok |
| Mensal = média das quinzenas, 16 componentes, 464 meses | | | recálculo | INPC: máx 0,0005 (arredondamento); demais: 0,0000 desde mar/1995, até 0,03 antes (retropolação do INEGI, já documentada) | ok |
| Incidências dos filhos somam a do pai, todos os períodos | | | recálculo | máx 0,0100 (jan/2011); quinzenal máx 0,0010 | ok |
| Cada nível de incidências soma a variação do INPC | | | recálculo | único caso acima de 0,01: jan/2011, nível 3, 0,0128 (já documentado) | ok |
| Variação no período, 12 meses, incidência (todos os períodos e componentes) | metricas_componentes | recálculo | data/raw | 0 | ok |
| Contribuição em 12 meses (identidade encadeada) | metricas_componentes | recálculo | data/raw | 5e-15 | ok |
| Nível soma a variação do INPC em 12 meses | | | recálculo | últimos 24 meses máx 0,0045 pp; histórico máx 0,0128 (2011) | ok |
| Contribuição no pai: filhos somam o pai, 7 pais, todos os períodos, incluindo jul-ago/2024 | | | recálculo | máx 4e-15 | ok |
| Contribuição no grupo (núcleo e não núcleo) | | | recálculo | máx 2e-15 | ok |
| Peso efetivo e incidência dos genéricos (24 meses, duas frequências) | metricas_genericos | recálculo com a planilha | data/raw | 6e-17 | ok |
| Soma das incidências dos genéricos por subíndice = incidência publicada | | | INEGI (3 casas) | máx 0,00014 pp | ok |
| Soma dos 292 = variação do INPC | | | INEGI | máx 0,0007 pp | ok |
| Mediana, p25 e p75 sazonais 2010-2019 dos 16 componentes | metricas_componentes | numpy.percentile | recálculo | 0 | ok |
| Mediana sazonal dos genéricos (último período) | 276 com mediana, 16 sem | numpy.median | recálculo | 0 | ok |
| Desvio sazonal ponderado = peso efetivo x (variação − mediana) | | | identidade | 3e-17 | ok |
| Difusão: % em alta, % acima de 3%, itens válidos e cobertura, 92 meses | metricas_difusao | recálculo com a cesta vigente | data/raw | 3e-14; cobertura mínima 97,3% (mês) e 93,6% (anual) | ok |
| STL no log, período 12, robusto, desde 2000 | series_dessazonalizadas | STL refeito | statsmodels | 0 | ok |
| Variação mensal SA, SAAR 3 e 6 meses | metricas_componentes | recálculo | | 0 | ok |
| Estimativa do mês, set/26: central, faixa e 12 meses (INPC e núcleo) | 0,4185 (0,3662 a 0,5040); 3,4518 | recálculo | | máx 4e-7 (o JSON guarda 6 casas) | ok |
| Cobertura da faixa fora da amostra | 50,0% de 56 (INPC); 48,2% de 56 (núcleo); 80 erros | recálculo | | 0 | ok |
| Backtest sem informação do futuro | mediana 2010-2019 fixa; erros só de meses anteriores ao atual; cobertura de cada mês só com erros anteriores | leitura do código e recálculo | | | ok |
| Aberturas: as 4 de maior peso de cada subíndice | | ordenação da planilha 2024 | | 0 | ok |
| Aberturas: 4 + "Demais" = variação em 12 meses do subíndice | | recálculo | | 4e-15; barras desde ago/25 | ok |

### O que aparece na tela

| o quê | tela | referência | fonte | diferença | ok |
|---|---|---|---|---|---|
| Faixa do release | 1ª quinzena set/26, divulgado 24/09 06:00, INPC 3,42%, Núcleo 3,79%, Não núcleo 2,17%, quinzena 0,33% | recálculo e calendário | data/raw | 0 | ok |
| Cartões e pílulas | INPC 3,42% / 0,33% / +0,16 pp; Núcleo 3,79% / 0,17% / −0,05 pp; Não núcleo 2,17% / 0,88% / +0,86 pp | recálculo | data/raw | 0 | ok |
| Estimativa do mês | 0,42%; 3,45%; faixa 0,37%–0,50%; 50% | recálculo | | 0 | ok |
| Destaques | SAAR 6m 3,90% (ago/26) vs 3,88%; Jitomate +0,11 pp (+22,79%); Jitomate +0,08 / Gasolina de bajo octanaje −0,02; 62% (ago/26) | recálculo e boletim | | 0 | ok |
| Tabela Últimos períodos (7 linhas x 4) | | recálculo | data/raw | 0 | ok |
| Tabelas de aberturas e de desvio sazonal | | boletim (quadro 2) e recálculo | | 0 | ok |
| Treemap (16 caixas) | | CA56 | INEGI | 15 iguais; Tarifas mostra +0,00 (valor 0,0046; o INEGI arredonda para 0,005) | ok (ver B4) |
| Soma das barras = linha, 21 gráficos de contribuição | | | DADOS do HTML | máx 4e-15 | ok |
| Etiqueta da ponta = último valor da série, 56 figuras | | | gráficos desenhados no Edge headless | nenhuma divergência | ok |
| Unidade: % nos gráficos, pp só no treemap | | | idem | nenhum "pp" em gráfico | ok |
| Eixo com a banda de 2% a 4% inteira nos 5 gráficos com meta | mínimo entre 1,38 e 1,5; máximo acima de 4,5 | | idem | | ok |
| Chip de período | "Mensal até ago/26 + 1ª quinz. set/26" nos gráficos com a quinzena; "Quinzenal · 1ª quinz. set/26" nos do release | dados de cada figura | | coerente | ok |
| Mistura de períodos | destaques de ritmo e difusão dizem "(ago/26)"; a estimativa diz "set/26" | | | nenhuma sem aviso no estado atual | ok (ver B1) |
| Offline, sem erro de JavaScript | 60 gráficos desenhados nas 4 abas | | Edge headless com a rede bloqueada | 0 erros (só a falha esperada do Google Fonts) | ok |
| Sem rolagem horizontal | 1440 e 390 px, 4 abas | | idem | largura do documento = largura da janela | ok (ver B3) |

### Bugs e casos de borda (simulados)

| o quê | resultado | ok |
|---|---|---|
| Estado depois de um release mensal (base até ago/26 e 2ª quinz. ago/26, tabulado quinzenal real da 2ª quinzena) | valida e monta; faixa, cartões, tabela e destaques certos; gráficos de meta com mistura de período | falha (B1) |
| Virada de ano: mensal de dez/25 e 1ª quinz. jan/26 (tabulado gerado da base, porque o INEGI só serve o release atual) | valida e monta; estimativa de jan/26 0,43% (faixa 0,38% a 0,52%, 50% de 48 meses); perfis sazonais com 2022 a 2025 | ok |
| Ingestão com relógio simulado: em dia, 06:00 e 05:59 do dia do release, base 3 e 7 meses atrasada, base vazia, depois do fim do calendário, jan/2027 | baixa só a janela, nada, a janela, o histórico completo e o aviso do calendário, como documentado | ok |
| Calendário só com o ano novo, antes do 1º release dele | `ultimo_divulgado` quebra com ValueError | falha (B6) |
| Próximo release nas bordas (05:59 e 06:00 do dia, depois de 23/12) | "hoje", o seguinte, "calendário 2027 ainda não carregado" | ok |
| Validação ainda falha quando deve (12 meses de Vivienda +0,02 no tabulado) | para com código 1 | ok |
| Clone limpo, venv novo, `pip install -r requirements.txt`, sem PYTHONIOENCODING, saída redirecionada | instala; do zero 292 s; incremental 12 s; data/processed e DADOS idênticos à base atual | ok |
| `IMPORTAR_DO_ZERO = True` num clone | histórico completo, 288 s, código 0 (num primeiro clone cujo `pip install` ficou incompleto; saída não comparada, refeito na reauditoria) | ok, parcial |
| Workflow: dia sem release, mensal, 1ª quinzena, 23/12, disparo manual com e sem release, jan/2027 | saídas `periodo` e `seguir` corretas | ok |
| Workflow: período já publicado por tentativa anterior | `ja=true` só quando o último commit automático é o do mesmo período | ok |
| Workflow: período ausente da base | sai com código 1 e a mensagem certa | ok |
| Workflow executado no GitHub | | não verificado: sem `gh` nesta máquina e a API pública não enxerga o repositório |
| Segurança: `.env` ignorado e nunca commitado; os dois valores do `.env` procurados em todas as revisões | 0 ocorrências em 27 commits; o código não lê token | ok |

## Bugs

| # | gravidade | o que acontece | causa | correção proposta |
|---|---|---|---|---|
| B1 | média | Depois de um release mensal, "INPC geral vs meta" e "Núcleo vs meta" rotulam a 2ª quinzena (núcleo 3,83% em ago/26) ao lado do cartão com o mês (3,88%), enquanto os outros gráficos param no mês. O subtítulo fixo diz "ponto destacado: última quinzena". Não aparece no estado atual. | `anual_com_meta` sempre acrescenta a quinzena; `tracos_da_serie` só acrescenta em release de quinzena | acrescentar o ponto só quando o release é de quinzena e deixar o subtítulo seguir a figura. Muda número na tela no estado mensal |
| B2 | média | No site, entre um release e outro, "em N dias" fica congelado no valor da montagem (montado em 27/09, diz "em 11 dias" até 08/10). | a contagem é feita no Python, e o HTML só é refeito no dia do release | calcular os dias no navegador a partir da data do próximo release. Muda número na tela |
| B3 | baixa | A 390 px, nos pares do Banxico e na aba Explorar, os anos do eixo x se sobrepõem ("2020202120222023"). | margem direita fixa de 196 px para as etiquetas deixa ~100 px de área útil com eixo anual | em tela estreita, eixo com passo maior e etiqueta só com o valor. Visual |
| B4 | baixa | O treemap escreve "+0,00 pp" (Tarifas do governo, 0,0046). | o sinal é decidido pelo valor sem arredondar | decidir o sinal pelo valor arredondado, como no resto do painel. Texto |
| B5 | baixa | Chip "Mensal · 2025–2025" nos gráficos de aberturas quando todo o intervalo cai num ano só (estado de dez/25). | o chip sempre escreve início–fim | escrever um ano só quando os dois são iguais. Texto |
| B6 | baixa | Se o calendário tiver só o ano novo e ainda não houve release nele, a ingestão quebra com ValueError; a montagem quebra do mesmo jeito se faltar a linha do último período da base. | as duas funções supõem que o calendário cobre a base | nenhuma no código (seria validação defensiva); o README já manda acrescentar linhas sem apagar as antigas |
| B7 | baixa | As tabelas "Contribuições por abertura" e "Desvio em relação à mediana sazonal" não dizem de que período são; os gráficos do release têm chip. | tabela não tem figura, e o chip sai da figura | chip com o período do release nas duas tabelas. Visual |
| B8 | sem efeito visível | `data-card="tend_momentum""` com aspas sobrando; `card.dataset.nota` nunca usado; comentários e docs apontam para `auditoria_pre_chat.md`. | sobra de versões anteriores | corrigir na limpeza |
| B9 | documentação | O guia diz que a fonte é Inter (é DM Sans) e que o momentum "avisa numa nota" (a nota saiu); `run_pipeline.py` diz "uns 8 minutos" (medi 5); `parametros.py` diz "rerodo todo o pipeline" onde é "baixo o histórico inteiro". | textos que ficaram para trás | corrigir na limpeza |
| B10 | ambiente | `.venv/` não está no `.gitignore`, e o guia manda criar o `.venv` dentro da pasta; num caminho de pasta muito longo (mais de 260 caracteres), o `pip install` do statsmodels falha pelo limite do Windows. | | pôr `.venv/` no `.gitignore`; o caminho longo não é do projeto e fica só anotado aqui |

O que foi feito com cada um:

- B1: corrigido. Em release mensal os gráficos de meta param no mês (núcleo 3,88%, o mesmo do cartão) e o subtítulo não fala mais em quinzena; no estado atual nada muda na tela.
- B2: corrigido depois da reauditoria. O navegador conta os dias no fuso da Cidade do México na hora em que a página abre; se o release já passou e o site não foi refeito, mostra "aguardando atualização". Conferido com o relógio simulado: 27/09 "em 11 dias", véspera "em 1 dia", 08/10 às 05:30 "hoje", 08/10 às 06:00 e 09/10 "aguardando atualização".
- B7: corrigido depois da reauditoria. As duas tabelas de aberturas ganharam o chip "Quinzenal · 1ª quinz. set/26", tirado dos destaques do resumo, de onde elas saem.
- B3: não corrigido, por decisão do autor.
- B4: corrigido no treemap e nas etiquetas dos gráficos; Tarifas do governo aparece "0,00 pp". Foi a única mudança na tela atual.
- B5, B8 e B10: corrigidos, sem efeito nos números.
- B6: fica como está.
- B9: corrigido na revisão do código e dos textos.

A auditoria anterior (`auditoria_pre_chat.md`) saiu. Os números que ela sustentava (backtest da estimativa do mês,
revisão do SAAR, difusão) estão resumidos na `metodologia.md` e foram reconferidos acima.

## Reauditoria

Depois das correções e da revisão do código e dos textos, rodei de novo todas as conferências acima, com os mesmos
scripts, sobre o código final:

- Tabulados, comunicados, BIE, colunas de 2024 e 2025, Banxico e calendário: os mesmos resultados, diferença zero.
- Identidades e métricas: 62 de 62 checagens dentro da tolerância, com as mesmas diferenças da primeira rodada.
- Tela: 46 de 46 números da faixa, cartões, destaques e tabela conferidos; 21 gráficos de contribuição somam a linha;
  60 gráficos desenhados nas 4 abas, a 1440 e 390 px, offline, sem erro de JavaScript e sem rolagem horizontal. As
  etiquetas, chips e eixos são os mesmos de antes da revisão, e os screenshots das 4 abas só diferem na hora de
  "Atualizado".
- Estados simulados (depois do release mensal, dez/25 e 1ª quinz. jan/26), ingestão com relógio simulado e os trechos
  do workflow: os mesmos resultados, agora com B1 e B5 corrigidos (no estado mensal, núcleo 3,88% no gráfico e no cartão).
- `data/processed` (13 arquivos) e o DADOS dos dois HTMLs, comparados com a cópia de antes da revisão: idênticos. No
  HTML, só mudou o comentário do topo do template.
- Clone limpo do código final, venv novo, sem variável de ambiente: `pip install` ok; do zero com o `False` commitado,
  273 s; incremental em seguida, 12 s ("Já atualizado"); com `IMPORTAR_DO_ZERO = True`, 259 s. As três rodadas
  deram `data/processed` e HTML idênticos aos do projeto.
- Continua não verificado: a execução do workflow no GitHub e o histórico completo dos 9 subíndices contra uma fonte
  externa.
