// Configuração do servidor, limite por IP e tradução dos erros do Gateway.
// O limite por IP daqui vive na memória de uma instância da função: segura rajadas, mas NÃO é limite global,
// porque a Vercel sobe várias instâncias. O teto global de gasto é o orçamento do AI Gateway (README), e o limite
// global por IP é uma regra de rate limit do Firewall da Vercel em /api/chat. As duas coisas ficam fora do código.

// ==== 1. Configuração (variáveis de ambiente, só no servidor) ====
const numero = (nome: string, padrao: number) => (process.env[nome] ? Number(process.env[nome]) : padrao);

export function configuracao() {
  return {
    chatAtivo: process.env.CHAT_ATIVO !== "false",  // interruptor: "false" desliga o chat e o dashboard continua no ar
    modelo: process.env.AI_MODEL || "anthropic/claude-sonnet-5",
    // na Vercel, sem chave, o Gateway autentica pelo OIDC do deploy; fora dela a chave é obrigatória
    temCredencial: Boolean(process.env.AI_GATEWAY_API_KEY || process.env.VERCEL),
    maxChamadasDados: numero("MAX_CHAMADAS_DADOS", 8),
    maxCenas: numero("MAX_CENAS", 3),
    maxTokensSaida: numero("MAX_TOKENS_SAIDA", 1200),
    timeoutMs: numero("TIMEOUT_MS", 60000),
    limitePorIp: numero("LIMITE_PEDIDOS_POR_IP", 30),
    janelaLimiteMs: numero("JANELA_LIMITE_MINUTOS", 10) * 60000,
    maxPassos: 10,  // chamadas ao modelo num pedido; o orçamento de ferramentas costuma parar antes
  };
}

// ==== 2. Limite por IP (por instância) ====
const pedidos = new Map<string, number[]>();

export function permitirPedido(ip: string, agora = Date.now()) {
  const { limitePorIp, janelaLimiteMs } = configuracao();
  const recentes = (pedidos.get(ip) ?? []).filter((t) => agora - t < janelaLimiteMs);
  if (recentes.length >= limitePorIp) return false;
  recentes.push(agora);
  pedidos.set(ip, recentes);
  if (pedidos.size > 5000) pedidos.delete(pedidos.keys().next().value!);
  return true;
}

export const ipDoPedido = (request: Request) => (request.headers.get("x-forwarded-for") ?? "local").split(",")[0].trim();

// ==== 3. Erros para o usuário, sem detalhe interno ====
export function mensagemDeErro(erro: unknown): string {
  const e = erro as { name?: string; statusCode?: number; message?: string };
  const texto = `${e?.name ?? ""} ${e?.message ?? ""}`.toLowerCase();
  if (e?.statusCode === 401 || e?.statusCode === 403 || texto.includes("authentication"))
    return "O AI Gateway recusou a credencial do servidor (AI_GATEWAY_API_KEY ou OIDC).";
  if (e?.statusCode === 402 || texto.includes("budget") || texto.includes("insufficient") || texto.includes("quota"))
    return "O orçamento de uso do AI Gateway acabou. O dashboard continua funcionando.";
  if (e?.statusCode === 429 || texto.includes("rate limit")) return "O AI Gateway limitou o uso agora. Tente de novo em alguns minutos.";
  if (texto.includes("timeout") || texto.includes("aborted")) return "A resposta passou do tempo limite e foi interrompida.";
  return "Falha ao consultar o modelo. O dashboard continua funcionando.";
}
