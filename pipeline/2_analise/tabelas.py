# Etapa 2.2: Tabelas
# Monta as tabelas do dashboard em HTML simples (<table class="tabela-dados">), sem estilo inline:
# números com 2 casas e vírgula decimal, "%" nas variações e "pp" nas contribuições, e a classe
# "positivo" ou "negativo" em cada célula numérica para o template colorir. Nada é calculado aqui:
# os números vêm prontos de metricas.py.
# Lê: data/processed (metricas_componentes, metricas_resumo); nomes curtos de config/parametros.py.
# Escreve: data/processed/tabelas.json = {slot: html}.

import html
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # para a etapa rodar sozinha: a raiz do projeto entra no caminho do Python
from config import parametros as p


# ==== 1. Células e tabela ====
def celula_numero(valor, unidade, casas=2):
    """Célula numérica com vírgula decimal, unidade e classe positivo/negativo (o INEGI publica incidências com 3 casas)."""
    sinal = " positivo" if valor > 0 else " negativo" if valor < 0 else ""
    texto = f"{valor:.{casas}f}".replace(".", ",") + unidade
    return f'<td class="numero{sinal}">{texto}</td>'


def celula_texto(texto, classe="texto"):
    """Célula de texto, com os caracteres especiais do HTML escapados."""
    return f'<td class="{classe}">{html.escape(str(texto))}</td>'


def tabela_html(cabecalho, linhas, titulo="", grupos=()):
    """Tabela completa: títulos das colunas, linhas já em HTML, título opcional e grupos de colunas opcionais [(texto, colunas)]."""
    titulos = "".join(f"<th>{html.escape(texto)}</th>" for texto in cabecalho)
    agrupados = "".join(f'<th colspan="{colunas}">{html.escape(texto)}</th>' for texto, colunas in grupos)
    cabecalho_html = (f'<tr class="grupo-colunas">{agrupados}</tr>' if grupos else "") + f"<tr>{titulos}</tr>"
    legenda = f"<caption>{html.escape(titulo)}</caption>" if titulo else ""
    return f'<table class="tabela-dados">{legenda}<thead>{cabecalho_html}</thead><tbody>{"".join(linhas)}</tbody></table>'


def grupo(titulo, colunas):
    """Linha de título de um bloco dentro da tabela (ex.: maiores e menores incidências)."""
    return f'<tr class="grupo"><th colspan="{colunas}">{html.escape(titulo)}</th></tr>'


# ==== 2. Tabelas do dashboard ====
def main_ultimos_periodos(componentes, resumo, nomes):
    """Variação no período nos 3 últimos períodos do último release e a variação em 12 meses do último."""
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
    """Os 5 genéricos que mais puxaram a inflação para cima e os 5 que mais puxaram para baixo, lado a lado."""
    tabelas = []
    for titulo, chave in (("Maiores incidências", "maiores_incidencias"), ("Menores incidências", "menores_incidencias")):
        linhas = [f"<tr>{celula_texto(item['nome_generico'], 'generico')}{celula_texto(nomes[item['subindice']], 'subindice')}"
                  f"{celula_numero(item['variacao_periodo'], '%')}{celula_numero(item['incidencia_periodo'], ' pp', 3)}</tr>"
                  for item in resumo["destaques"][chave]]
        tabelas.append(tabela_html(["Genérico", "Subíndice", "Variação", "Incidência"], linhas, titulo))
    return f'<div class="lado-a-lado">{"".join(tabelas)}</div>'


def decomp_desvios(componentes, resumo, nomes):
    """Os genéricos cujo movimento fora do normal mais pesou no INPC, para cima e para baixo."""
    linhas = []
    for titulo, chave in (("Acima da norma", "acima_da_norma"), ("Abaixo da norma", "abaixo_da_norma")):
        linhas.append(grupo(titulo, 5))
        for item in resumo["destaques"][chave]:
            linhas.append(f"<tr>{celula_texto(item['nome_generico'], 'generico')}{celula_numero(item['variacao_periodo'], '%')}"
                          f"{celula_numero(item['norma_mediana'], '%')}{celula_numero(item['desvio_norma'], ' pp')}"
                          f"{celula_numero(item['contribuicao_surpresa'], ' pp', 3)}</tr>")
    return tabela_html(["Genérico", "Variação", "Norma", "Desvio", "Contribuição da surpresa"], linhas)


if __name__ == "__main__":
    inicio = time.time()
    componentes = pd.read_parquet(p.PASTA_PROCESSED / "metricas_componentes.parquet")
    nomes = p.NOMES_EXIBICAO
    resumo = json.loads((p.PASTA_PROCESSED / "metricas_resumo.json").read_text(encoding="utf-8"))
    tabelas = {slot.__name__: slot(componentes, resumo, nomes) for slot in (main_ultimos_periodos, main_top_incidencias, decomp_desvios)}
    (p.PASTA_PROCESSED / "tabelas.json").write_text(json.dumps(tabelas, ensure_ascii=False), encoding="utf-8")
    print(f"Tabelas: {len(tabelas)} tabelas; {time.time() - inicio:.1f} s")
