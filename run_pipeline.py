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

PIPELINE = Path(__file__).resolve().parent / "pipeline"
DEPOIS_DA_INGESTAO = ["1_dados/tratamento.py", "1_dados/validacao.py", "1_dados/dessazonalizacao.py",
                      "2_analise/metricas.py", "2_analise/tabelas.py", "2_analise/graficos.py"]

leitor = argparse.ArgumentParser()
leitor.add_argument("--completo", action="store_true", help="baixa todo o histórico de novo")
completo = leitor.parse_args().completo

inicio = time.time()
ingestao = runpy.run_path(str(PIPELINE / "1_dados/ingestao.py"), init_globals={"completo": completo}, run_name="__main__")
if ingestao["base_mudou"]:
    for etapa in DEPOIS_DA_INGESTAO:
        runpy.run_path(str(PIPELINE / etapa), run_name="__main__")
# a montagem roda sempre: mesmo sem dado novo, atualiza o horário e a contagem até o próximo release
runpy.run_path(str(PIPELINE / "3_dashboard/montagem.py"), run_name="__main__")
print(f"Pipeline: {time.time() - inicio:.1f} s")
