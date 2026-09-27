# Etapa 2.2: Tabelas
# Transformo em HTML as três tabelas do dashboard. Não calculo nada aqui: os números já vêm prontos
# das métricas, e eu só escolho quais entram, formato com vírgula decimal e o sufixo certo ("%" para
# variação, "pp" para contribuição) e marco cada número como positivo ou negativo. Os textos falam a
# língua do leitor brasileiro: incidência vira contribuição, genérico vira abertura, subíndice vira
# grupo e norma vira mediana sazonal. O visual fica por conta do template.

import html
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para rodar a etapa sozinha, a raiz do projeto precisa estar no caminho
from config import parametros as p


# ==== 1. Células e tabela ====
def celula_numero(valor, unidade):
    """Célula de número já no formato brasileiro, com 2 casas em tudo, que é o padrão do IBGE para variação e contribuição."""
    valor = round(valor, 2) or 0.0  # o que arredonda para zero sai "0,00", sem sinal e sem cor
    sinal = " positivo" if valor > 0 else " negativo" if valor < 0 else ""
    texto = f"{valor:.2f}".replace("-", "−").replace(".", ",") + unidade  # "−" tipográfico, o mesmo dos cartões
    return f'<td class="numero{sinal}">{texto}</td>'


def celula_texto(texto, classe="texto"):
    """Célula de texto, com o que for especial em HTML escapado."""
    return f'<td class="{classe}">{html.escape(str(texto))}</td>'


def tabela_html(cabecalho, linhas, titulo="", grupos=()):
    """Monta a tabela inteira; os grupos, se houver, viram uma linha de cabeçalho por cima, tipo "Variação no período"."""
    titulos = "".join(f"<th>{html.escape(texto)}</th>" for texto in cabecalho)
    agrupados = "".join(f'<th colspan="{colunas}">{html.escape(texto)}</th>' for texto, colunas in grupos)
    cabecalho_html = (f'<tr class="grupo-colunas">{agrupados}</tr>' if grupos else "") + f"<tr>{titulos}</tr>"
    legenda = f"<caption>{html.escape(titulo)}</caption>" if titulo else ""
    return f'<table class="tabela-dados">{legenda}<thead>{cabecalho_html}</thead><tbody>{"".join(linhas)}</tbody></table>'


def grupo(titulo, colunas):
    """Uma linha de título no meio da tabela, para separar blocos como "acima" e "abaixo" da mediana."""
    return f'<tr class="grupo"><th colspan="{colunas}">{html.escape(titulo)}</th></tr>'


# ==== 2. Tabelas do dashboard ====
def main_ultimos_periodos(componentes, resumo):
    """O último release: a variação no período contra o padrão sazonal, e a taxa em 12 meses agora e um mês antes."""
    # responde às duas perguntas do dia: o dado surpreendeu (variação contra a mediana de 2010-2019) e acelerou
    # (12 meses contra um mês antes: a 1a quinzena do mês anterior, ou o mês anterior)
    frequencia = resumo["frequencia_do_release"]
    da_frequencia = componentes[componentes["frequencia"] == frequencia].set_index(["componente", "posicao"])
    fim = da_frequencia.index.get_level_values("posicao").max()
    antes = fim - p.PERIODOS_POR_ANO[frequencia] // 12
    rotulos = da_frequencia.loc["indice_general"]
    cabecalho = ["Componente", "Variação", "Padrão sazonal", rotulos.at[fim, "rotulo_curto"], rotulos.at[antes, "rotulo_curto"]]
    linhas = []
    for componente in (*p.COMPONENTES_PRINCIPAIS, *p.COMPONENTES_NIVEL_2):
        atual, anterior = da_frequencia.loc[(componente, fim)], da_frequencia.loc[(componente, antes)]
        celulas = [celula_numero(valor, "%") for valor in (atual["variacao_periodo"], atual["norma_mediana"], atual["variacao_anual"], anterior["variacao_anual"])]
        linhas.append(f"<tr>{celula_texto(p.NOMES_EXIBICAO[componente], 'componente')}{''.join(celulas)}</tr>")
    return tabela_html(cabecalho, linhas, grupos=[("", 1), (rotulos.at[fim, "rotulo_periodo"], 2), ("12 meses", 2)])


def periodo_das_aberturas(resumo):
    """O período das duas tabelas de aberturas, para o chip do card: "Quinzenal · 1ª quinz. set/26"."""
    destaques = resumo["destaques"]
    return html.escape(f"{destaques['frequencia'].capitalize()} · {destaques['rotulo_periodo']}")


def main_top_incidencias(resumo):
    """Os cinco genéricos que mais puxaram a inflação para cima e os cinco que mais seguraram, em duas tabelas."""
    tabelas = []
    for titulo, chave in (("Maiores contribuições", "maiores_incidencias"), ("Menores contribuições", "menores_incidencias")):
        linhas = [f"<tr>{celula_texto(item['nome_generico'], 'generico')}{celula_texto(p.NOMES_EXIBICAO[item['subindice']], 'subindice')}"
                  f"{celula_numero(item['variacao_periodo'], '%')}{celula_numero(item['incidencia_periodo'], ' pp')}</tr>"
                  for item in resumo["destaques"][chave]]
        tabelas.append(tabela_html(["Abertura", "Grupo", "Variação", "Contribuição"], linhas, titulo))
    return f'<div class="lado-a-lado" data-periodo="{periodo_das_aberturas(resumo)}">{"".join(tabelas)}</div>'


def decomp_desvios(resumo):
    """Os genéricos cujo desvio contra a mediana sazonal, vezes o peso efetivo, mais pesou no INPC, para cima e para baixo."""
    linhas = []
    for titulo, chave in (("Acima da mediana sazonal", "acima_da_norma"), ("Abaixo da mediana sazonal", "abaixo_da_norma")):
        linhas.append(grupo(titulo, 5))
        for item in resumo["destaques"][chave]:
            linhas.append(f"<tr>{celula_texto(item['nome_generico'], 'generico')}{celula_texto(p.NOMES_EXIBICAO[item['subindice']], 'subindice')}"
                          f"{celula_numero(item['variacao_periodo'], '%')}{celula_numero(item['norma_mediana'], '%')}"
                          f"{celula_numero(item['desvio_sazonal_ponderado'], ' pp')}</tr>")
    tabela = tabela_html(["Abertura", "Grupo", "Variação", "Mediana sazonal", "Desvio sazonal ponderado"], linhas)
    return f'<div data-periodo="{periodo_das_aberturas(resumo)}">{tabela}</div>'


if __name__ == "__main__":
    inicio = time.time()
    componentes = pd.read_parquet(p.PASTA_PROCESSED / "metricas_componentes.parquet")
    resumo = json.loads((p.PASTA_PROCESSED / "metricas_resumo.json").read_text(encoding="utf-8"))
    # a chave de cada tabela é o data-card do espaço dela no template
    tabelas = {"main_ultimos_periodos": main_ultimos_periodos(componentes, resumo),
               "main_top_incidencias": main_top_incidencias(resumo),
               "decomp_desvios": decomp_desvios(resumo)}
    (p.PASTA_PROCESSED / "tabelas.json").write_text(json.dumps(tabelas, ensure_ascii=False), encoding="utf-8")
    print(f"Tabelas: {len(tabelas)} tabelas; {time.time() - inicio:.1f} s")
