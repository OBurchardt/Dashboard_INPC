// Apoio dos testes: um modelo simulado que segue um roteiro de passos (texto e chamadas de ferramenta), o pedido
// padrão do painel e a leitura do SSE. Tudo aqui é simulação: nenhum teste deste diretório avalia o modelo real.

import { simulateReadableStream, type LanguageModel } from "ai";
import { MockLanguageModelV4 } from "ai/test";
import { executarFerramenta, type FerramentaDeDados } from "../lib/ferramentas.js";
import { carregarPacote } from "../lib/pacote.js";

export const pacote = carregarPacote();
export const contexto = { pacote, estado: { aba: "resumo", visualizacao_em_foco: null, destaque: null, revisao: 0 }, acompanhar: true };
export const executar = (nome: FerramentaDeDados, entrada: unknown) => executarFerramenta(contexto, nome, entrada);

// ==== Modelo simulado ====
type Chunk = Record<string, unknown>;
export type Chamada = { prompt: any[]; tools?: { name: string }[] };
const uso = { inputTokens: { total: 10, noCache: 10, cacheRead: undefined, cacheWrite: undefined }, outputTokens: { total: 10, text: 10, reasoning: undefined } };

export const texto = (t: string, id = "t" + Math.random().toString(36).slice(2, 7)): Chunk[] =>
  [{ type: "text-start", id }, ...t.match(/.{1,12}/gs)!.map((d) => ({ type: "text-delta", id, delta: d })), { type: "text-end", id }];
export const chamar = (toolName: string, input: unknown, toolCallId = "c" + Math.random().toString(36).slice(2, 8)): Chunk[] =>
  // como os provedores reais: a entrada chega em pedaços e depois vem a chamada completa
  [{ type: "tool-input-start", id: toolCallId, toolName }, { type: "tool-input-delta", id: toolCallId, delta: JSON.stringify(input) },
   { type: "tool-input-end", id: toolCallId }, { type: "tool-call", toolCallId, toolName, input: JSON.stringify(input) }];
const fim = (motivo: "stop" | "tool-calls"): Chunk => ({ type: "finish", finishReason: { unified: motivo, raw: undefined }, usage: uso });

export function modeloComRoteiro(passos: ((chamada: Chamada) => Chunk[])[], opcoes: { atrasoMs?: number; erro?: unknown } = {}) {
  // cada chamada ao modelo usa o próximo passo do roteiro; o último se repete
  const chamadas: Chamada[] = [];
  const modelo = new MockLanguageModelV4({
    doStream: async (chamada: any) => {
      chamadas.push(chamada);
      if (opcoes.erro) throw opcoes.erro;
      const partes = passos[Math.min(chamadas.length - 1, passos.length - 1)](chamada);
      const motivo = partes.some((p) => p.type === "tool-call") ? "tool-calls" : "stop";
      return { stream: simulateReadableStream({ chunks: [...partes, fim(motivo)], chunkDelayInMs: opcoes.atrasoMs ?? 0 }) as any };
    },
  }) as unknown as LanguageModel;
  return { modelo, chamadas };
}

// ==== Pedido e resposta ====
export function pedido(pergunta: string, extra: Record<string, unknown> = {}) {
  return {
    snapshot_id: pacote.snapshot_id, acompanhar: true,
    estado_tela: { aba: "resumo", visualizacao_em_foco: null, destaque: null, revisao: 0 },
    mensagens: [{ id: "u1", role: "user", parts: [{ type: "text", text: pergunta }] }], ...extra,
  };
}

export function requisicao(corpo: unknown, headers: Record<string, string> = {}, signal?: AbortSignal) {
  return new Request("http://localhost/api/chat", { method: "POST", body: typeof corpo === "string" ? corpo : JSON.stringify(corpo),
    headers: { "content-type": "application/json", "x-forwarded-for": "10.0.0.1", ...headers }, signal });
}

export async function eventos(resposta: Response): Promise<any[]> {
  const bruto = await resposta.text();
  return bruto.split("\n\n").map((b) => b.replace(/^data: /, "").trim()).filter((b) => b && b !== "[DONE]").map((b) => JSON.parse(b));
}

export const textoDaResposta = (lista: any[]) => lista.filter((e) => e.type === "text-delta").map((e) => e.delta).join("");
export const verificacaoDa = (lista: any[]) => lista.find((e) => e.type === "data-verificacao")?.data;
