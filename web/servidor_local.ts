// Servidor para rodar a versão online em localhost (npm run local): serve public/ e as duas rotas da API com a
// mesma lógica das funções da Vercel. Lê web/.env se existir; a chave nunca é impressa. Os testes de navegador
// sobem este mesmo servidor com um modelo simulado no lugar do Gateway.

import { existsSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { pathToFileURL } from "node:url";
import type { LanguageModel } from "ai";
import { estadoDoServico, responderChat } from "./lib/chat.js";

const TIPOS: Record<string, string> = { ".html": "text/html; charset=utf-8", ".json": "application/json", ".js": "text/javascript" };

export function criarServidor(dependencias: { modelo?: LanguageModel; semApi?: boolean } = {}) {
  return createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    if (url.pathname.startsWith("/api/")) {
      if (dependencias.semApi) { res.writeHead(502); return res.end(); }  // simula o backend fora do ar
      // a requisição do Node vira um Request da web, e o cancelamento do navegador chega como abortSignal
      const cancelar = new AbortController();
      res.on("close", () => { if (!res.writableFinished) cancelar.abort(); });
      const corpo = req.method === "POST" ? await new Promise<string>((ok) => { let t = ""; req.on("data", (c) => (t += c)); req.on("end", () => ok(t)); }) : undefined;
      const headers = new Headers(Object.entries(req.headers).flatMap(([k, v]) => (typeof v === "string" ? [[k, v]] : [])) as [string, string][]);
      const pedido = new Request(new URL(url.pathname, `http://${req.headers.host}`), { method: req.method, headers, body: corpo, signal: cancelar.signal });
      const resposta = url.pathname === "/api/chat" ? await responderChat(pedido, { modelo: dependencias.modelo })
        : url.pathname === "/api/estado" ? estadoDoServico({ modelo: dependencias.modelo }) : new Response("não encontrado", { status: 404 });
      res.writeHead(resposta.status, Object.fromEntries(resposta.headers));
      try { if (resposta.body) for await (const pedaco of resposta.body as any) res.write(pedaco); } catch { /* o navegador cancelou */ }
      return res.end();
    }
    const caminho = normalize(join("public", url.pathname === "/" ? "index.html" : url.pathname));
    if (!caminho.startsWith("public") || !existsSync(caminho)) { res.writeHead(404); return res.end("não encontrado"); }
    res.writeHead(200, { "content-type": TIPOS[extname(caminho)] ?? "application/octet-stream" });
    res.end(readFileSync(caminho));
  });
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (existsSync(".env")) process.loadEnvFile(".env");
  const porta = Number(process.env.PORTA ?? 3000);
  criarServidor().listen(porta, () => console.log(`Versão online local em http://localhost:${porta}`));
}
