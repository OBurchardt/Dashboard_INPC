// O leitor de SSE do painel, a função real tirada do template: pedaço de rede não é evento, e caractere acentuado
// pode chegar partido em dois pedaços.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const template = readFileSync(new URL("../../pipeline/3_dashboard/template.html", import.meta.url), "utf-8");
const fonte = /async function\* eventosDoStream[\s\S]*?\r?\n\}\r?\n/.exec(template)![0];
const eventosDoStream = new Function(`return (${fonte.trim()})`)() as (r: { body: ReadableStream }, s: AbortSignal) => AsyncGenerator<any>;

function respostaEmPedacos(pedacos: Uint8Array[]) {
  return { body: new ReadableStream({ start(c) { pedacos.forEach((p) => c.enqueue(p)); c.close(); } }) };
}

test("eventos partidos em pedaços arbitrários e acentos partidos no meio do byte", async () => {
  const sse = ['data: {"type":"text-delta","id":"a","delta":"inflação em 12 meses: ação"}', 'data: {"type":"data-verificacao","data":{"status":"verificada"}}', "data: [DONE]"]
    .map((l) => l + "\n\n").join("");
  const bytes = new TextEncoder().encode(sse);
  // corto em pedaços de 7 bytes: o "ç" e o "ã" (2 bytes cada) caem partidos em algum corte
  const pedacos = [];
  for (let i = 0; i < bytes.length; i += 7) pedacos.push(bytes.slice(i, i + 7));
  const lidos = [];
  for await (const e of eventosDoStream(respostaEmPedacos(pedacos), new AbortController().signal)) lidos.push(e);
  assert.equal(lidos.length, 2);
  assert.equal(lidos[0].delta, "inflação em 12 meses: ação");
  assert.equal(lidos[1].data.status, "verificada");
});

test("para no [DONE] e respeita o cancelamento", async () => {
  const bytes = new TextEncoder().encode('data: {"type":"start"}\n\ndata: [DONE]\n\ndata: {"type":"depois"}\n\n');
  const lidos = [];
  for await (const e of eventosDoStream(respostaEmPedacos([bytes]), new AbortController().signal)) lidos.push(e.type);
  assert.deepEqual(lidos, ["start"]);
  const cancelado = new AbortController();
  cancelado.abort();
  const nada = [];
  for await (const e of eventosDoStream(respostaEmPedacos([bytes]), cancelado.signal)) nada.push(e);
  assert.equal(nada.length, 0);
});
