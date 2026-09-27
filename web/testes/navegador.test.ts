// O painel no navegador de verdade (Edge, via Playwright), com o servidor local e um modelo simulado por roteiro.
// Confere o que só aparece na tela: o HTML offline, o backend fora do ar, a navegação confirmada depois do plotly,
// a mudança manual durante a resposta, o botão de parar, o teclado, o redimensionamento e o texto sem HTML do modelo.

import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { after, before, test } from "node:test";
import { chromium, type Browser, type Page } from "playwright-core";
import type { LanguageModel } from "ai";
import { criarServidor } from "../servidor_local.js";
import { chamar, executar, modeloComRoteiro, texto } from "./apoio.js";

let navegador: Browser;
before(async () => { navegador = await chromium.launch({ channel: "msedge", headless: true }); });
after(async () => { await navegador.close(); });

async function abrir(opcoes: { modelo?: LanguageModel; semApi?: boolean; largura?: number } = {}) {
  process.env.LIMITE_PEDIDOS_POR_IP = "1000";
  const servidor = criarServidor(opcoes);
  await new Promise<void>((ok) => servidor.listen(0, ok));
  const pagina = await navegador.newPage({ viewport: { width: opcoes.largura ?? 1440, height: 900 } });
  const erros: string[] = [];
  pagina.on("pageerror", (e) => erros.push(e.message));
  await pagina.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());  // a fonte vem de fora; o teste não depende dela
  await pagina.goto(`http://localhost:${(servidor.address() as AddressInfo).port}/`);
  await pagina.waitForSelector("#resumo .js-plotly-plot");
  return { pagina, erros, fechar: async () => { await pagina.close(); servidor.closeAllConnections(); servidor.close(); } };
}

async function perguntar(pagina: Page, pergunta: string) {
  await pagina.click("#abrir-assistente");
  await pagina.waitForFunction(() => !document.getElementById("assistente-enviar")!.hasAttribute("disabled"));
  await pagina.fill("#assistente-pergunta", pergunta);
  await pagina.keyboard.press("Enter");
}

test("HTML aberto do disco: dashboard funciona e o painel aponta a versão online, sem chamar servidor", async () => {
  const pagina = await navegador.newPage({ viewport: { width: 1440, height: 900 } });
  const erros: string[] = [];
  pagina.on("pageerror", (e) => erros.push(e.message));
  const pedidos: string[] = [];
  pagina.on("request", (r) => { if (!r.url().startsWith("file:")) pedidos.push(r.url()); });
  await pagina.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await pagina.goto(new URL("../../output/index.html", import.meta.url).href);
  await pagina.waitForSelector("#resumo .js-plotly-plot");
  await pagina.click("#abrir-assistente");
  const aviso = await pagina.textContent("#assistente-mensagens");
  assert.match(aviso!, /A análise com IA exige conexão/);
  assert.match(await pagina.getAttribute("#assistente-mensagens a", "href") ?? "", /^https:\/\/.+\.vercel\.app/);
  assert.ok(await pagina.isDisabled("#assistente-enviar"));
  assert.ok(!pedidos.some((u) => u.includes("/api/")));
  assert.deepEqual(erros, []);
  await pagina.close();
});

test("backend fora do ar: dashboard intacto e aviso específico com tentar novamente", async () => {
  const { pagina, erros, fechar } = await abrir({ semApi: true });
  await pagina.click("#abrir-assistente");
  await pagina.waitForSelector("[data-reverificar]");
  assert.match(await pagina.textContent("#assistente-mensagens") ?? "", /O dashboard funciona normalmente/);
  await pagina.click('.abas button[data-aba="composicao"]');
  await pagina.waitForSelector("#composicao .js-plotly-plot");
  assert.deepEqual(erros, []);
  await fechar();
});

test("item: consulta, abre o bloco real no Explorar com a série destacada, e o texto cita evidências clicáveis", async () => {
  const consulta = { series: ["g070"], metricas: ["variacao_periodo", "incidencia_periodo"], frequencia: "quinzenal" };
  const [variacao, incidencia] = executar("consultar_dados", consulta).evidencias;
  const { modelo } = modeloComRoteiro([
    () => chamar("consultar_dados", consulta),
    () => chamar("controlar_dashboard", { acao: "mostrar", visualizacao: "explorar_frutas_y_verduras_anual", destacar_serie: "g070" }),
    () => texto(`O Jitomate subiu 22,79% [${variacao.id}] na quinzena e contribuiu com 0,11 pp [${incidencia.id}] para o INPC.`),
  ]);
  const { pagina, erros, fechar } = await abrir({ modelo });
  await perguntar(pagina, "E o jitomate?");
  await pagina.waitForSelector(".verificacao", { timeout: 15000 });
  assert.equal(await pagina.getAttribute('.abas button[data-aba="explorar"]', "class"), "ativa");
  const card = pagina.locator('#explorar [data-card="explorar_frutas_y_verduras_anual"]');
  assert.match(await card.getAttribute("class") ?? "", /em-foco/);
  // e está de fato na tela, não só marcado: os gráficos do Explorar desenham sob demanda e empurram o layout
  const posicao = (await card.boundingBox())!;
  assert.ok(posicao.y >= 60 && posicao.y + posicao.height <= 900, `card em y=${posicao.y}`);
  assert.ok(await pagina.locator("#assistente-sugestoes").isHidden());
  // o destaque é real: no gráfico desenhado, só os traços do Jitomate ficam opacos
  const opacidades = await card.locator("[data-grafico]").evaluate((div: any) => div.data.map((t: any) => [t.name.split(" · ")[0], t.opacity]));
  assert.ok(opacidades.filter(([n]: any) => n === "Jitomate").every(([, o]: any) => o === 1));
  assert.ok(opacidades.filter(([n]: any) => n !== "Jitomate").every(([, o]: any) => o === 0.2));
  assert.match(await pagina.textContent("#assistente-mensagens") ?? "", /Aberto no dashboard/);
  assert.match(await pagina.textContent(".verificacao") ?? "", /Números conferidos/);
  // o painel não cobre o gráfico que está sendo explicado
  const caixaCard = (await card.boundingBox())!, caixaPainel = (await pagina.locator("#assistente").boundingBox())!;
  assert.ok(caixaCard.x + caixaCard.width <= caixaPainel.x + 1);
  await pagina.click(".evidencia >> nth=0");
  assert.match(await pagina.textContent(".detalhe-evidencia") ?? "", /22,79%/);
  assert.deepEqual(erros, []);
  await fechar();
});

test("mudança manual de aba durante a resposta: a ação atrasada não passa por cima", async () => {
  const { modelo } = modeloComRoteiro([
    () => chamar("consultar_contexto", {}),
    () => chamar("controlar_dashboard", { acao: "mostrar", visualizacao: "tend_momentum" }),
    () => texto("Não mudei a tela porque você trocou de aba."),
  ], { atrasoMs: 120 });
  const { pagina, fechar } = await abrir({ modelo });
  await perguntar(pagina, "Como está o núcleo?");
  await pagina.click('.abas button[data-aba="composicao"]');
  await pagina.waitForSelector(".atividade.falha", { timeout: 15000 });
  assert.match(await pagina.textContent(".atividade.falha") ?? "", /mudou a tela durante a resposta/);
  assert.equal(await pagina.getAttribute('.abas button[data-aba="composicao"]', "class"), "ativa");
  await fechar();
});

test("parar interrompe a resposta e libera o envio", async () => {
  const { modelo } = modeloComRoteiro([() => texto("uma leitura longa do núcleo ".repeat(60))], { atrasoMs: 40 });
  const { pagina, fechar } = await abrir({ modelo });
  await perguntar(pagina, "Como está o núcleo?");
  await pagina.waitForFunction(() => document.getElementById("assistente-enviar")!.textContent === "Parar");
  await pagina.click("#assistente-enviar");
  await pagina.waitForSelector("text=Resposta interrompida.");
  assert.equal(await pagina.textContent("#assistente-enviar"), "Enviar");
  await fechar();
});

test("teclado, foco e plotly redimensionado ao abrir e fechar o painel", async () => {
  const { pagina, fechar } = await abrir({ modelo: modeloComRoteiro([() => texto("ok")]).modelo });
  // o desenho do plotly tem de ter a largura do espaço dele, antes e depois de o painel mudar a área útil
  const larguras = () => pagina.locator('#resumo [data-grafico="main_inpc_meta"]').evaluate((div) =>
    [div.querySelector(".main-svg")!.getBoundingClientRect().width, div.clientWidth]);
  const [antes] = await larguras();
  await pagina.focus("#abrir-assistente");
  await pagina.keyboard.press("Enter");
  await pagina.waitForFunction(() => document.activeElement?.id === "assistente-pergunta");
  await pagina.waitForTimeout(400);
  const [desenho, espaco] = await larguras();
  assert.ok(Math.abs(desenho - espaco) < 2, `${desenho} vs ${espaco}`);
  assert.ok(Math.abs(desenho - antes) > 50);
  await pagina.keyboard.press("Escape");
  await pagina.waitForFunction(() => document.activeElement?.id === "abrir-assistente");
  await pagina.waitForTimeout(400);
  assert.ok(Math.abs((await larguras())[0] - antes) < 2);
  await fechar();
});

test("texto do modelo não vira HTML nem link", async () => {
  const { modelo } = modeloComRoteiro([() => texto('Veja <img src=x onerror="window.invadido=1"> e [clique](https://exemplo.com) **aqui**.')]);
  const { pagina, fechar } = await abrir({ modelo });
  await perguntar(pagina, "?");
  await pagina.waitForSelector(".verificacao");
  assert.equal(await pagina.locator("#assistente-mensagens img").count(), 0);
  assert.equal(await pagina.locator("#assistente-mensagens .assistente-resposta a").count(), 0);
  assert.equal(await pagina.evaluate(() => (window as any).invadido), undefined);
  assert.equal(await pagina.locator("#assistente-mensagens strong").count(), 1);
  await fechar();
});

test("tela pequena: painel ocupa a tela e oferece voltar ao gráfico depois da ação", async () => {
  const { modelo } = modeloComRoteiro([() => chamar("controlar_dashboard", { acao: "mostrar", visualizacao: "tend_difusao" }), () => texto("Abri a difusão.")]);
  const { pagina, fechar } = await abrir({ modelo, largura: 390 });
  await perguntar(pagina, "Mostre a difusão");
  await pagina.waitForSelector("[data-fechar-para-ver]", { timeout: 15000 });
  assert.equal(Math.round((await pagina.locator("#assistente").boundingBox())!.width), 390);
  await pagina.click("[data-fechar-para-ver]");
  assert.ok(await pagina.locator("#assistente").isHidden());
  assert.ok(await pagina.locator('#composicao [data-card="tend_difusao"]').isVisible());
  await fechar();
});
