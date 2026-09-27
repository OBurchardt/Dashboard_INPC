// A rota /api/chat. Recebe a conversa do painel, confere tudo, chama o modelo pelo AI Gateway e devolve o stream
// de mensagens do AI SDK (SSE): texto, andamento das ferramentas, evidências nos resultados, pedido de ação de tela,
// erro e fim, mais uma parte "data-verificacao" que diz se os números do texto batem com as evidências.
// Regras que valem aqui e em nenhum outro lugar: o system prompt é só o do servidor; o histórico do navegador não
// vale como prova, então todo resultado de ferramenta de dados que vem nele é refeito a partir do pacote; o turno
// (a pergunta e suas continuações depois de cada cena) tem orçamento de 8 consultas e 3 cenas.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  convertToModelMessages, createUIMessageStream, createUIMessageStreamResponse, isStepCount, streamText, toUIMessageStream, tool,
  type LanguageModel, type ToolSet, type UIMessage,
} from "ai";
import { z } from "zod";
import {
  executarFerramenta, FERRAMENTAS_DE_DADOS, resultadoDaAcao, schemaControlarDashboard, schemas,
  type Contexto, type EstadoTela, type FerramentaDeDados,
} from "./ferramentas.js";
import { configuracao, ipDoPedido, mensagemDeErro, permitirPedido } from "./limites.js";
import { carregarPacote, envelope, type Envelope, type Evidencia, type Pacote } from "./pacote.js";
import { verificarResposta } from "./verificacao.js";

// ==== 1. O pedido ====
const parteDeFerramenta = z.object({
  type: z.string().regex(/^tool-[a-z_]+$/), toolCallId: z.string().min(1).max(80),
  state: z.enum(["input-streaming", "input-available", "output-available", "output-error"]),
  input: z.unknown().optional(), output: z.unknown().optional(), errorText: z.string().max(500).optional(),
});
const pedidoSchema = z.strictObject({
  snapshot_id: z.string().max(40),
  acompanhar: z.boolean(),
  estado_tela: z.strictObject({ aba: z.string().max(30), visualizacao_em_foco: z.string().max(80).nullable(), destaque: z.string().max(80).nullable(),
                                revisao: z.number().int().min(0) }),
  mensagens: z.array(z.discriminatedUnion("role", [
    z.object({ id: z.string().max(80), role: z.literal("user"), parts: z.array(z.strictObject({ type: z.literal("text"), text: z.string().min(1).max(2000) })).min(1).max(3) }),
    z.object({ id: z.string().max(80), role: z.literal("assistant"), parts: z.array(z.union([
      z.object({ type: z.literal("text"), text: z.string().max(12000) }),
      z.object({ type: z.literal("step-start") }),
      z.object({ type: z.string().regex(/^data-[a-z_]+$/) }),
      parteDeFerramenta,
    ])).max(80) }),
  ])).min(1).max(30),
});
type Pedido = z.infer<typeof pedidoSchema>;

const erroJson = (status: number, erro: string, mensagem: string, extra: Record<string, unknown> = {}) =>
  Response.json({ erro, mensagem, ...extra }, { status });

// ==== 2. O histórico, refeito no servidor ====
const ehDados = (nome: string): nome is FerramentaDeDados => (FERRAMENTAS_DE_DADOS as readonly string[]).includes(nome);

function turnoAtual(mensagens: Pedido["mensagens"]) {
  // o turno lógico começa na última pergunta; as mensagens do assistente depois dela são as continuações das cenas
  const inicio = mensagens.map((m) => m.role).lastIndexOf("user");
  return mensagens.slice(inicio + 1);
}

function historicoRefeito(pedido: Pedido, contexto: Contexto) {
  // o que o navegador manda como resultado de consulta é descartado e recalculado a partir do pacote (com cache);
  // da ação de tela só aceito o contrato do resultado, sem nenhum número econômico. Chamada que ficou sem resposta
  // (o usuário parou antes de a tela responder) vira "cancelled", para o modelo saber que não aconteceu
  const evidencias = new Map<string, Evidencia>();
  let chamadasDados = 0, cenas = 0, houveAcaoAplicada = false, textoDoTurno = "";
  const doTurno = new Set(turnoAtual(pedido.mensagens));
  const mensagens: UIMessage[] = pedido.mensagens.map((m) => {
    if (m.role === "user") return { id: m.id, role: "user", parts: m.parts };
    const parts = m.parts.flatMap((parte): any[] => {
      if (parte.type === "text") { if (doTurno.has(m)) textoDoTurno += (parte as { text: string }).text; return [parte]; }
      if (parte.type === "step-start" || parte.type.startsWith("data-")) return [];
      const p = parte as z.infer<typeof parteDeFerramenta>;
      const nome = p.type.slice(5);
      if (p.state === "input-streaming") return [];
      if (ehDados(nome)) {
        const resultado = executarFerramenta(contexto, nome, p.input);
        if (doTurno.has(m)) { chamadasDados++; resultado.evidencias.forEach((ev) => evidencias.set(ev.id, ev)); }
        return [{ type: p.type, toolCallId: p.toolCallId, state: "output-available", input: p.input ?? {}, output: resultado }];
      }
      if (nome === "controlar_dashboard") {
        if (doTurno.has(m)) cenas++;
        const saida = p.state === "output-available" ? resultadoDaAcao.safeParse(p.output) : null;
        const output = saida?.success ? saida.data
          : { status: p.state === "input-available" ? "cancelled" : "error", action_id: p.toolCallId, estado_aplicado: null, mensagem: "sem resultado válido da tela" };
        if (doTurno.has(m) && output.status === "applied") houveAcaoAplicada = true;
        return [{ type: p.type, toolCallId: p.toolCallId, state: "output-available", input: p.input ?? {}, output }];
      }
      return [];  // ferramenta que não existe: some do histórico
    });
    return { id: m.id, role: "assistant", parts };
  });
  return { mensagens, evidencias, chamadasDados, cenas, houveAcaoAplicada, textoDoTurno };
}

// ==== 3. As ferramentas deste pedido ====
const DESCRICOES: Record<FerramentaDeDados | "controlar_dashboard", string> = {
  consultar_contexto: "Snapshot, divulgação ativa (1ª quinzena, ou mensal + 2ª quinzena), estado da tela do usuário (aba, visualização em foco, destaque), visualizações registradas, cobertura, expectativas registradas e limitações. Use no começo e para resolver 'esse dado', 'agora', 'isso'.",
  buscar_series: "Acha séries no catálogo (16 componentes, 292 genéricos, itens que saíram da cesta 2018 e a difusão) por nome oficial em espanhol ou apelido em português. Devolve candidatos com id, hierarquia, cobertura e métricas, e diz se o termo é ambíguo.",
  consultar_dados: "Valores de séries por id, métrica, frequência e intervalo, com unidade, validação e evidências. Série fora da cobertura ou métrica inexistente volta como indisponível, nunca como zero.",
  analisar_componentes: "Análises determinísticas já calculadas pelo pipeline: ranking (por incidência, variação ou desvio sazonal, critério explícito), decomposição (partes, total, soma e resíduo, sem somar o pai aos filhos), comparação temporal (mudança da taxa em pp), comparação sazonal (mesmo mês ou quinzena em 2010–2019, com n, mediana, p25 e p75), tendência (12 meses, SAAR, dessazonalizada e difusão até o último mês fechado, sem nota; é a análise para 'o núcleo melhorou?') e exclusão contábil (INPC do período menos as contribuições retiradas; não é índice reponderado).",
  consultar_metodologia: "Trechos versionados de docs/metodologia.md, docs/guia_do_projeto.md e docs/auditoria.md por tema: definição, fórmula documentada, fonte, cobertura, limitações e validação. Os temas 'expectativas' e 'estimativa_do_mes' trazem também os valores registrados, com evidências.",
  controlar_dashboard: "Executa UMA cena no dashboard do usuário: abrir a aba e rolar até uma visualização registrada, destacando uma série ou linha; desfazer a última mudança; ou restaurar a visão inicial. Roda no navegador e volta com status applied, unsupported, stale_state, cancelled ou error. Só diga que algo está na tela depois de applied. Confirmação de tela não valida número.",
};

function ferramentas(contexto: Contexto, contador: { dados: number; limite: number }): ToolSet {
  const deDados = Object.fromEntries(FERRAMENTAS_DE_DADOS.map((nome) => [nome, tool({
    description: DESCRICOES[nome], inputSchema: schemas[nome] as z.ZodType<any>,
    execute: async (entrada: unknown): Promise<Envelope> => {
      // o orçamento é por turno lógico, contando as continuações; acabou, a ferramenta não roda e diz isso ao modelo
      if (contador.dados >= contador.limite)
        return envelope(contexto.pacote, "orcamento_esgotado", { limite: contador.limite, orientacao: "Responda com o que já consultou e diga o que ficou de fora." });
      contador.dados++;
      return executarFerramenta(contexto, nome, entrada);
    },
  })]));
  return { ...deDados, controlar_dashboard: tool({ description: DESCRICOES.controlar_dashboard, inputSchema: schemaControlarDashboard(contexto.pacote) }) };
}

// ==== 4. A rota ====
let promptDoSistema: string | null = null;
const lerPrompt = () => (promptDoSistema ??= readFileSync(join(process.cwd(), "prompt_sistema.md"), "utf-8"));

export async function responderChat(request: Request, dependencias: { modelo?: LanguageModel; pacote?: Pacote } = {}): Promise<Response> {
  const inicio = Date.now();
  const config = configuracao();
  if (request.method !== "POST") return erroJson(405, "metodo", "Use POST.");
  // só a própria página conversa com o servidor: sem CORS, e "Origin: null" (arquivo aberto do disco) é recusado
  const origem = request.headers.get("origin");
  if (origem && origem !== new URL(request.url).origin) return erroJson(403, "origem", "Origem não permitida.");
  if (!config.chatAtivo) return erroJson(503, "chat_desligado", "O assistente está desligado neste momento. O dashboard continua funcionando.");
  if (!dependencias.modelo && !config.temCredencial)
    return erroJson(503, "sem_credencial", "O servidor não tem credencial do AI Gateway.", { variavel: "AI_GATEWAY_API_KEY" });
  if (!permitirPedido(ipDoPedido(request))) return erroJson(429, "limite", "Muitas perguntas em pouco tempo. Tente de novo em alguns minutos.");
  const bruto = await request.text();
  if (bruto.length > 200_000) return erroJson(413, "tamanho", "Conversa longa demais; comece uma nova.");
  let json: unknown;
  try { json = JSON.parse(bruto); } catch { return erroJson(400, "json", "Pedido inválido."); }
  const validado = pedidoSchema.safeParse(json);
  if (!validado.success) return erroJson(400, "pedido_invalido", "Pedido fora do formato.", { detalhe: z.prettifyError(validado.error).slice(0, 500) });
  const pedido = validado.data;
  const pacote = dependencias.pacote ?? carregarPacote();
  // o painel foi montado com um snapshot; se o servidor tem outro, a análise para aqui
  if (pedido.snapshot_id !== pacote.snapshot_id)
    return erroJson(409, "snapshot_divergente", "O dashboard aberto é de outro snapshot dos dados. Recarregue a página.", { snapshot_servidor: pacote.snapshot_id });
  if (pedido.mensagens[pedido.mensagens.length - 1].role === "user" && pedido.mensagens.filter((m) => m.role === "user").length > 12)
    return erroJson(413, "tamanho", "Conversa longa demais; comece uma nova.");

  const contexto: Contexto = { pacote, estado: pedido.estado_tela as EstadoTela, acompanhar: pedido.acompanhar };
  const historico = historicoRefeito(pedido, contexto);
  const contador = { dados: historico.chamadasDados, limite: config.maxChamadasDados };
  const conjunto = ferramentas(contexto, contador);
  const podeNavegar = () => pedido.acompanhar && historico.cenas < config.maxCenas;
  const ativas = (): string[] => [...(contador.dados < contador.limite ? FERRAMENTAS_DE_DADOS : []), ...(podeNavegar() ? ["controlar_dashboard"] : [])];

  const stream = createUIMessageStream({
    onError: mensagemDeErro,
    execute: async ({ writer }) => {
      const resultado = streamText({
        model: dependencias.modelo ?? config.modelo,
        instructions: lerPrompt(),
        messages: await convertToModelMessages(historico.mensagens, { tools: conjunto, ignoreIncompleteToolCalls: true }),
        tools: conjunto, activeTools: ativas(),
        prepareStep: () => ({ activeTools: ativas() }),
        stopWhen: isStepCount(config.maxPassos),
        maxOutputTokens: config.maxTokensSaida, timeout: { totalMs: config.timeoutMs }, maxRetries: 1,
        abortSignal: request.signal,
        // cache de prompt do Gateway: o system prompt e as ferramentas se repetem a cada passo e custam 10% no cache
        providerOptions: { gateway: { caching: "auto" } },
        // o SDK imprimiria o erro inteiro; no log fica só o tipo e o status
        onError: ({ error }) => console.log(JSON.stringify({ evento: "erro_modelo", tipo: (error as Error)?.name, status: (error as { statusCode?: number })?.statusCode ?? null })),
      });
      let texto = historico.textoDoTurno, cenaPendente = false, passos = 0;
      for await (const parte of toUIMessageStream({ stream: resultado.stream, sendFinish: false, onError: mensagemDeErro })) {
        if (parte.type === "text-delta") texto += parte.delta;
        if (parte.type === "finish-step") passos++;
        if (parte.type === "tool-output-available") ((parte.output as Envelope)?.evidencias ?? []).forEach((ev) => historico.evidencias.set(ev.id, ev));
        if (parte.type === "tool-input-available" && parte.toolName === "controlar_dashboard") cenaPendente = true;
        writer.write(parte);
      }
      // com uma cena pendente o turno continua depois da resposta da tela; a conferência vem no fim do turno
      if (!cenaPendente) writer.write({ type: "data-verificacao", data: verificarResposta(texto, historico.evidencias, historico.houveAcaoAplicada) });
      writer.write({ type: "finish" });
      // diagnóstico só com metadados: nada da conversa, nada de chave
      const uso = await Promise.resolve(resultado.totalUsage).catch(() => undefined);
      console.log(JSON.stringify({ evento: "chat", snapshot: pacote.snapshot_id, passos, chamadas_dados: contador.dados, cenas: historico.cenas + Number(cenaPendente),
                                   tokens_entrada: uso?.inputTokens ?? null, tokens_cache: uso?.inputTokenDetails?.cacheReadTokens ?? null,
                                   tokens_saida: uso?.outputTokens ?? null, duracao_ms: Date.now() - inicio }));
    },
  });
  return createUIMessageStreamResponse({ stream });
}

export function estadoDoServico(dependencias: { pacote?: Pacote; modelo?: LanguageModel } = {}) {
  // o painel pergunta isto ao abrir: se o chat está ligado e com qual snapshot; nenhum segredo sai daqui
  const config = configuracao();
  const pacote = dependencias.pacote ?? carregarPacote();
  const motivo = !config.chatAtivo ? "chat_desligado" : !config.temCredencial && !dependencias.modelo ? "sem_credencial" : null;
  return Response.json({ chat_disponivel: !motivo, motivo, snapshot_id: pacote.snapshot_id, release: pacote.release.rotulo });
}
