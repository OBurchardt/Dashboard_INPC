# Este é o botão de rodar: python run_pipeline.py. Ele chama as oito etapas em ordem, cada uma
# pelo caminho do arquivo, porque as pastas começam com número e o Python não importa nome assim.
# Cada etapa lê e escreve arquivos em data/, então também dá para rodar uma sozinha
# (python pipeline/1_dados/tratamento.py) quando eu só mexi nela.

import runpy
import time
from pathlib import Path

# False: só traz o dado mais recente; em dia sem release nem chega a ir à rede.
# True: rebaixa o histórico inteiro do INEGI como se a base não existisse (uns 8 minutos).
IMPORTAR_DO_ZERO = False

PIPELINE = Path(__file__).resolve().parent / "pipeline"
ETAPAS = ["1_dados/ingestao.py", "1_dados/tratamento.py", "1_dados/validacao.py", "1_dados/dessazonalizacao.py",
          "2_analise/metricas.py", "2_analise/tabelas.py", "2_analise/graficos.py", "3_dashboard/montagem.py"]

inicio = time.time()
# depois da ingestão tudo roda sempre, porque leva segundos e assim qualquer mudança no código aparece no dashboard;
# se a validação falhar ela interrompe tudo antes da montagem, e o dashboard de antes (que foi validado) fica valendo
for etapa in ETAPAS:
    runpy.run_path(str(PIPELINE / etapa), init_globals={"importar_do_zero": IMPORTAR_DO_ZERO}, run_name="__main__")
print(f"Pipeline: {time.time() - inicio:.1f} s")
