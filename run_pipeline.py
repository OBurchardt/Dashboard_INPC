# Orquestrador do pipeline do INPC (México).
# Roda as etapas na ordem, cada uma pelo caminho do arquivo (as pastas começam com número,
# então não dá para importá-las). Cada etapa também roda sozinha: python pipeline/1_dados/tratamento.py
#   python run_pipeline.py

import runpy
import time
from pathlib import Path

# False: só atualiza a base com o dado mais recente (em dia sem release, nem vai à rede).
# True: rebaixa todo o histórico do INEGI como se a base não existisse (uns 8 minutos).
IMPORTAR_DO_ZERO = False

PIPELINE = Path(__file__).resolve().parent / "pipeline"
ETAPAS = ["1_dados/ingestao.py", "1_dados/tratamento.py", "1_dados/validacao.py", "1_dados/dessazonalizacao.py",
          "2_analise/metricas.py", "2_analise/tabelas.py", "2_analise/graficos.py", "3_dashboard/montagem.py"]

inicio = time.time()
# depois da ingestão tudo roda sempre (leva segundos), para qualquer mudança no código chegar ao dashboard;
# se a validação falhar, ela para o pipeline antes da montagem e o dashboard anterior, já validado, fica
for etapa in ETAPAS:
    runpy.run_path(str(PIPELINE / etapa), init_globals={"importar_do_zero": IMPORTAR_DO_ZERO}, run_name="__main__")
print(f"Pipeline: {time.time() - inicio:.1f} s")
