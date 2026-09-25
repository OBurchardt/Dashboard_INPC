# Regras permanentes do projeto

- Siga a árvore definida no README.md. Não crie arquivos, pastas, utils, scripts de teste ou notebooks fora dela sem perguntar antes.
- Um arquivo por etapa, com várias funções dentro, ordenadas na sequência em que são usadas.
- Parâmetros e escolhas vivem em config/. Nada de números mágicos no código do pipeline.
- Etapas não importam umas das outras; comunicam-se por arquivos em data/. A única exceção é config/parametros.py, que todas podem ler.
- O projeto precisa rodar do zero com `python run_pipeline.py --completo`.
- Nomes em português, completos, sem acento e sem abreviação.
- Toda função tem docstring curta em português: o que recebe, o que devolve, a fonte do dado.
- O token nunca aparece no código nem em logs; é lido de INEGI_TOKEN no .env.
- Testes exploratórios rodam no terminal e não ficam salvos em arquivo.
- Ao terminar qualquer tarefa, liste os arquivos criados ou alterados.
