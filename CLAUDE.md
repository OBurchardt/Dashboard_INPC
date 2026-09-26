# Regras permanentes do projeto

- Siga a árvore definida no README.md. Não crie arquivos, pastas, utils, scripts de teste ou notebooks fora dela sem perguntar antes.
- Um arquivo por etapa, com várias funções dentro, ordenadas na sequência em que são usadas.
- Parâmetros que um humano ajusta (caminhos, URLs, ids, janelas) vivem em config/parametros.py.
- Etapas não importam umas das outras; comunicam-se por arquivos em data/. A única exceção é config/parametros.py, que todas podem ler.
- O projeto precisa rodar do zero com `python run_pipeline.py`, com `IMPORTAR_DO_ZERO = True` no topo do arquivo.
- Nomes em português, completos, sem acento e sem abreviação.
- Toda função tem docstring curta em português: o que recebe, o que devolve, a fonte do dado.
- Nenhuma fonte atual exige token. Se alguma vier a exigir, o token fica só no .env e nunca aparece no código nem em logs.
- Testes exploratórios rodam no terminal e não ficam salvos em arquivo.
- Ao terminar qualquer tarefa, liste os arquivos criados ou alterados.

## Estilo de código

- Código para humano ler. Simplicidade vale mais que robustez. Se eu não entender o arquivo lendo de cima para baixo em poucos minutos, está errado.
- Cada arquivo começa com um bloco de comentário, em português simples, dizendo o que a etapa faz e por quê (5 a 10 linhas).
- O arquivo é dividido em seções com cabeçalho (`# ==== 1. Nome da seção ====`), na ordem em que rodam.
- Funções curtas, uma responsabilidade cada, nome que diz o que faz. Docstring de uma linha.
- Comentários explicam o PORQUÊ e o significado econômico, não repetem o código. Bom: "# o índice mensal é a média das duas quinzenas". Ruim: "# lê o arquivo".
- Proibido sem eu pedir: logging (use print de uma linha por etapa), classes, try/except genérico, validações defensivas, hash, manifesto, pastas temporárias, código comentado, constantes que só são usadas uma vez.
- Única exceção: chamadas de rede com retentativa simples (até 3 tentativas), porque o servidor do INEGI derruba conexões.
- Nada de lógica duplicada entre arquivos: cada coisa é feita em um lugar só.
