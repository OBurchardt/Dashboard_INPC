# Orquestrador do pipeline do INPC (México).
# Roda as etapas na ordem, cada uma pelo caminho do arquivo (as pastas começam com número,
# então não dá para importá-las). Rodar daqui também deixa a raiz do projeto no caminho do
# Python, o que permite a todas as etapas fazer "from config import parametros".
#   python run_pipeline.py              atualiza só se o calendário diz que saiu dado novo
#   python run_pipeline.py --completo   reconstrói a base inteira

import argparse
import runpy
import time
from pathlib import Path

ETAPAS = Path(__file__).resolve().parent / "pipeline" / "1_dados"

leitor = argparse.ArgumentParser()
leitor.add_argument("--completo", action="store_true", help="baixa todo o histórico de novo")
completo = leitor.parse_args().completo

inicio = time.time()
ingestao = runpy.run_path(str(ETAPAS / "ingestao.py"), init_globals={"completo": completo}, run_name="__main__")
if ingestao["base_mudou"]:
    runpy.run_path(str(ETAPAS / "tratamento.py"), run_name="__main__")
    runpy.run_path(str(ETAPAS / "validacao.py"), run_name="__main__")
print(f"Pipeline: {time.time() - inicio:.1f} s")
# Próximas etapas: dessazonalizacao, metricas, tabelas e graficos, montagem.
