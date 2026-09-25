"""
Orquestrador do pipeline do INPC (México).

Executa cada etapa pelo caminho do arquivo (runpy.run_path), não por import,
porque as pastas das etapas começam com número. As etapas se comunicam apenas
por arquivos em data/.

Ordem das etapas:
    1. pipeline/1_dados/ingestao.py
    2. pipeline/1_dados/tratamento.py
    3. pipeline/1_dados/validacao.py        (para o pipeline se uma checagem crítica falhar)
    4. pipeline/1_dados/dessazonalizacao.py
    5. pipeline/2_analise/metricas.py
    6. pipeline/2_analise/tabelas.py
    7. pipeline/2_analise/graficos.py
    8. pipeline/3_dashboard/montagem.py

Modos:
    python run_pipeline.py --completo
        Reconstrói tudo do zero: ingestão em modo completo (histórico inteiro)
        e todas as etapas seguintes.

    python run_pipeline.py
        Padrão. Consulta config/calendario_releases.csv. Se não houve release
        desde o último dado da base, não chama a rede e avisa "já atualizado".
        Senão, roda a ingestão em modo atualização e recalcula as etapas
        seguintes.

Status: ingestão, tratamento e validação implementados.
"""

import argparse
import logging
import runpy
import time
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent
PASTA_PIPELINE = RAIZ_PROJETO / "pipeline"


def executar_etapa(caminho_relativo, **variaveis):
    """Recebe o caminho da etapa (relativo a pipeline/) e variáveis a injetar; executa o script, registra o tempo e devolve seus globais."""
    inicio = time.time()
    globais = runpy.run_path(str(PASTA_PIPELINE / caminho_relativo), init_globals=variaveis, run_name="__main__")
    logging.getLogger("pipeline").info("== etapa %s: %.1f s", caminho_relativo, time.time() - inicio)
    return globais


def principal():
    """Não recebe nada (lê --completo da linha de comando); executa as etapas implementadas na ordem. Não devolve nada."""
    leitor = argparse.ArgumentParser(description="Pipeline do INPC (INEGI)")
    leitor.add_argument("--completo", action="store_true", help="reconstrói data/raw com o histórico inteiro")
    argumentos = leitor.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    modo = "completo" if argumentos.completo else "atualizacao"
    inicio = time.time()
    resultado = executar_etapa("1_dados/ingestao.py", modo_execucao=modo)["resultado_ingestao"]
    if resultado["status"] == "ja_atualizado":
        return

    executar_etapa("1_dados/tratamento.py")
    executar_etapa("1_dados/validacao.py")
    logging.getLogger("pipeline").info("== pipeline concluído em %.1f s", time.time() - inicio)
    # executar_etapa("1_dados/dessazonalizacao.py")
    # executar_etapa("2_analise/metricas.py")
    # executar_etapa("2_analise/tabelas.py")
    # executar_etapa("2_analise/graficos.py")
    # executar_etapa("3_dashboard/montagem.py")


if __name__ == "__main__":
    principal()
