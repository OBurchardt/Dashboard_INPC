# Dashboard da inflação do México (INPC)

Pipeline em Python que baixa as séries do Índice Nacional de Preços ao Consumidor (INPC) diretamente do INEGI, trata, dessazonaliza, valida contra os números oficiais, calcula métricas analíticas e gera um dashboard HTML autocontido. O dashboard é aberto por um economista no momento do release (06:00, horário da Cidade do México) e se atualiza de forma automática e reproduzível.

## Estrutura

```
README.md                           visão geral do projeto (este arquivo)
CLAUDE.md                           regras permanentes do projeto
run_pipeline.py                     orquestra as etapas na ordem; IMPORTAR_DO_ZERO no topo
requirements.txt                    dependências Python
.gitignore                          arquivos fora do controle de versão
config/
  parametros.py                     caminhos, fuso, URLs e ids do INEGI, janela de atualização
  catalogo_series.csv               lista das séries do INEGI a baixar
  calendario_releases.csv           calendário oficial de divulgação do INPC
pipeline/
  1_dados/
    ingestao.py                     baixa do INEGI (app indicesdeprecios, ponderadores, tabulados) para data/raw/
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
  guia_do_projeto.md                guia completo: como rodar, fluxo, fórmulas, dicionário de dados, páginas
  auditoria_pre_chat.md             auditoria antes do chat: problemas, evidências, correções e testes de falha
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

## Ver ao vivo

O site na Vercel serve o `output/index.html` da branch `main`. Cada commit na main que muda esse arquivo
publica a versão nova; o `dashboard_inpc.html` é o mesmo HTML, para abrir offline ou mandar por e-mail.

## Rodar no GitHub

Na aba Actions do repositório, o workflow "Atualizar dashboard do INPC" tem o botão "Run workflow". Ele instala
as dependências numa máquina limpa, roda `python run_pipeline.py` (com a base vazia, a ingestão baixa o histórico
inteiro), falha se a validação falhar e guarda `dashboard_inpc.html` como artefato para baixar. Não há disparo
automático nem publicação: o HTML só fica disponível no próprio job.

## Calendário do ano seguinte

O `config/calendario_releases.csv` só tem os releases de 2026; depois do último, o dashboard avisa que falta o calendário.
Quando o INEGI publicar o calendário do ano seguinte, acrescente uma linha por release no mesmo formato
(data, 06:00, America/Mexico_City, tipo e mês de referência) e rode o pipeline normalmente.
