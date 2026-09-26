# Etapa 2.2: Tabelas
# Transformo em HTML as três tabelas do dashboard. Não calculo nada aqui: os números já vêm prontos
# das métricas, e eu só escolho quais entram, formato com vírgula decimal e o sufixo certo ("%" para
# variação, "pp" para contribuição) e marco cada número como positivo ou negativo. Os textos da tela
# falam a língua do leitor brasileiro: incidência vira contribuição, genérico vira abertura, subíndice
# vira grupo e norma vira mediana sazonal. O que eu chamava de surpresa é só o desvio contra a mediana de
# 2010 a 2019, e não contra expectativa de mercado; a tela diz isso. O visual fica por conta do template.

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
    """Uma linha de título no meio da tabela, para separar blocos como "acima" e "abaixo" da norma."""
    return f'<tr class="grupo"><th colspan="{colunas}">{html.escape(titulo)}</th></tr>'


# ==== 2. Tabelas do dashboard ====
def main_ultimos_periodos(componentes, resumo, nomes):
    """Os três últimos períodos do release lado a lado, mais a variação em 12 meses do mais recente."""
    frequencia = resumo["frequencia_do_release"]
    da_frequencia = componentes[componentes["frequencia"] == frequencia]
    periodos = sorted(da_frequencia["periodo"].unique())[-3:]
    valores = da_frequencia[da_frequencia["periodo"].isin(periodos)].set_index(["componente", "periodo"])
    rotulos = da_frequencia.drop_duplicates("periodo").set_index("periodo")["rotulo_curto"]
    cabecalho = ["Componente"] + [rotulos[periodo] for periodo in periodos] + [rotulos[periodos[-1]]]
    linhas = []
    for componente in (*p.COMPONENTES_PRINCIPAIS, *p.COMPONENTES_NIVEL_2):
        celulas = [celula_numero(valores.at[(componente, periodo), "variacao_periodo"], "%") for periodo in periodos]
        celulas.append(celula_numero(valores.at[(componente, periodos[-1]), "variacao_anual"], "%"))
        linhas.append(f"<tr>{celula_texto(nomes[componente], 'componente')}{''.join(celulas)}</tr>")
    return tabela_html(cabecalho, linhas, grupos=[("", 1), ("Variação no período", 3), ("12 meses", 1)])


def main_top_incidencias(componentes, resumo, nomes):
    """Os cinco genéricos que mais puxaram a inflação para cima e os cinco que mais seguraram, em duas tabelas."""
    tabelas = []
    for titulo, chave in (("Maiores contribuições", "maiores_incidencias"), ("Menores contribuições", "menores_incidencias")):
        linhas = [f"<tr>{celula_texto(item['nome_generico'], 'generico')}{celula_texto(nomes[item['subindice']], 'subindice')}"
                  f"{celula_numero(item['variacao_periodo'], '%')}{celula_numero(item['incidencia_periodo'], ' pp')}</tr>"
                  for item in resumo["destaques"][chave]]
        tabelas.append(tabela_html(["Abertura", "Grupo", "Variação", "Contribuição"], linhas, titulo))
    return f'<div class="lado-a-lado">{"".join(tabelas)}</div>'


def decomp_desvios(componentes, resumo, nomes):
    """Os genéricos cujo desvio contra a mediana sazonal, vezes o peso efetivo, mais pesou no INPC, para cima e para baixo."""
    linhas = []
    for titulo, chave in (("Acima da mediana sazonal", "acima_da_norma"), ("Abaixo da mediana sazonal", "abaixo_da_norma")):
        linhas.append(grupo(titulo, 5))
        for item in resumo["destaques"][chave]:
            linhas.append(f"<tr>{celula_texto(item['nome_generico'], 'generico')}{celula_texto(nomes[item['subindice']], 'subindice')}"
                          f"{celula_numero(item['variacao_periodo'], '%')}{celula_numero(item['norma_mediana'], '%')}"
                          f"{celula_numero(item['desvio_sazonal_ponderado'], ' pp')}</tr>")
    return tabela_html(["Abertura", "Grupo", "Variação", "Mediana sazonal", "Desvio sazonal ponderado"], linhas)


if __name__ == "__main__":
    inicio = time.time()
    componentes = pd.read_parquet(p.PASTA_PROCESSED / "metricas_componentes.parquet")
    nomes = p.NOMES_EXIBICAO
    resumo = json.loads((p.PASTA_PROCESSED / "metricas_resumo.json").read_text(encoding="utf-8"))
    tabelas = {slot.__name__: slot(componentes, resumo, nomes) for slot in (main_ultimos_periodos, main_top_incidencias, decomp_desvios)}
    (p.PASTA_PROCESSED / "tabelas.json").write_text(json.dumps(tabelas, ensure_ascii=False), encoding="utf-8")
    print(f"Tabelas: {len(tabelas)} tabelas; {time.time() - inicio:.1f} s")
