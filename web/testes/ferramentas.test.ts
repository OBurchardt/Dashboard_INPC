// Ferramentas de dados sobre o pacote real. As referências são números publicados pelo INEGI (boletim da
// 1ª quinz. set/26, quadros 1 e 2) e pelo Banxico (Informe Trimestral abr-jun/2026), os mesmos que a
// docs/auditoria.md conferiu contra o pipeline; nenhuma referência é recalculada com a lógica testada.

import assert from "node:assert/strict";
import { test } from "node:test";
import { schemaControlarDashboard } from "../lib/ferramentas.js";
import { executar, pacote } from "./apoio.js";

const r2 = (v: number) => Math.round(v * 100) / 100;
const dados = (e: { dados: unknown }) => e.dados as any;

test("snapshot e release do pacote", () => {
  assert.match(pacote.snapshot_id, /^[0-9a-f]{16}$/);
  assert.equal(pacote.release.periodo, "2026-09-Q1");
  assert.equal(pacote.release.frequencia_do_release, "quinzenal");
});

test("tomate é ambíguo entre jitomate e tomate verde; jitomate e tomate verde resolvem sozinhos", () => {
  const tomate = executar("buscar_series", { termo: "tomate" });
  assert.equal(tomate.status, "ambiguo");
  const exatas = dados(tomate).candidatos.filter((c: any) => c.correspondencia === "exata").map((c: any) => c.id).sort();
  assert.deepEqual(exatas, ["g070", "g076"]);
  assert.equal(dados(executar("buscar_series", { termo: "jitomate" })).candidatos[0].id, "g070");
  assert.equal(executar("buscar_series", { termo: "jitomate" }).status, "ok");
  assert.equal(dados(executar("buscar_series", { termo: "Tomate verde" })).candidatos[0].id, "g076");
});

test("núcleo, core e serviços resolvem para o componente, não para um genérico", () => {
  for (const [termo, id] of [["núcleo", "subyacente"], ["core", "subyacente"], ["serviços", "servicios"], ["inflação cheia", "indice_general"]]) {
    const r = executar("buscar_series", { termo });
    assert.equal(r.status, "ok", termo);
    assert.equal(dados(r).candidatos[0].id, id, termo);
  }
});

test("termo sem correspondência exata não escolhe sozinho", () => {
  assert.equal(executar("buscar_series", { termo: "gasolina" }).status, "baixa_confianca");
  assert.equal(executar("buscar_series", { termo: "bitcoin" }).status, "indisponivel");
});

test("ranking por incidência é o do boletim e difere do ranking por variação", () => {
  const base = { operacao: "ranking", universo: "genericos", direcao: "maiores", frequencia: "quinzenal" };
  const incidencia = dados(executar("analisar_componentes", { ...base, criterio: "incidencia_periodo" })).lista;
  const variacao = dados(executar("analisar_componentes", { ...base, criterio: "variacao_periodo" })).lista;
  // boletim 1q2026_09, quadro 2
  assert.deepEqual(incidencia.map((x: any) => x.nome), ["Jitomate", "Primaria", "Cebolla", "Gas doméstico LP", "Pollo"]);
  assert.equal(Math.round(incidencia[0].valor * 1000) / 1000, 0.105);
  assert.notDeepEqual(variacao.map((x: any) => x.nome), incidencia.map((x: any) => x.nome));
  const menores = dados(executar("analisar_componentes", { ...base, direcao: "menores", criterio: "incidencia_periodo" })).lista;
  assert.deepEqual(menores.map((x: any) => x.nome), ["Servicios profesionales", "Papa y otros tubérculos", "Tequila", "Productos para el cabello", "Automóviles"]);
});

test("unidades, sinais e frequência", () => {
  const r = executar("consultar_dados", { series: ["g070", "g292"], metricas: ["variacao_periodo", "incidencia_periodo"], frequencia: "quinzenal" });
  const jitomate = dados(r).series.g070.metricas, profissionais = dados(r).series.g292.metricas;
  assert.equal(jitomate.variacao_periodo.unidade, "%");
  assert.equal(jitomate.incidencia_periodo.unidade, "pp");
  assert.equal(r2(jitomate.variacao_periodo.valores[0].valor), 22.79);
  assert.ok(profissionais.incidencia_periodo.valores[0].valor < 0);
  assert.equal(Math.round(profissionais.incidencia_periodo.valores[0].valor * 1000) / 1000, -0.043);
  for (const ev of r.evidencias) assert.ok(ev.frequencia === "quinzenal" && ev.periodo === "2026-09-Q1");
});

test("quinzenal, mensal e 12 meses não se confundem", () => {
  const q = dados(executar("consultar_dados", { series: ["indice_general", "subyacente"], metricas: ["variacao_periodo", "variacao_anual"], frequencia: "quinzenal" }));
  assert.equal(r2(q.series.indice_general.metricas.variacao_periodo.valores[0].valor), 0.33);
  assert.equal(r2(q.series.indice_general.metricas.variacao_anual.valores[0].valor), 3.42);
  assert.equal(r2(q.series.subyacente.metricas.variacao_anual.valores[0].valor), 3.79);
  const m = dados(executar("consultar_dados", { series: ["indice_general"], metricas: ["variacao_anual"], frequencia: "mensal" }));
  assert.equal(m.series.indice_general.metricas.variacao_anual.valores[0].periodo, "2026-08");
  assert.equal(r2(m.series.indice_general.metricas.variacao_anual.valores[0].valor), 3.26);
  // setembro fechado ainda não existe no dia da 1ª quinzena
  const setembro = dados(executar("consultar_dados", { series: ["indice_general"], metricas: ["variacao_anual"], frequencia: "mensal", inicio: "2026-09" }));
  assert.equal(setembro.series.indice_general.metricas.variacao_anual.status, "fora_da_cobertura");
});

test("comparação sazonal equivalente: mesma quinzena, 2010–2019, com n e faixa", () => {
  const inpc = dados(executar("analisar_componentes", { operacao: "comparacao_sazonal", serie: "indice_general", frequencia: "quinzenal" }));
  assert.equal(inpc.posicao_no_ano, "09-Q1");
  assert.deepEqual([r2(inpc.mediana), r2(inpc.p25), r2(inpc.p75)], [0.32, 0.23, 0.34]);  // guia do projeto, seção de métricas
  assert.equal(inpc.n, 10);
  const jitomate = dados(executar("analisar_componentes", { operacao: "comparacao_sazonal", serie: "g070", frequencia: "quinzenal" }));
  assert.equal(r2(jitomate.mediana), 5.46);
  assert.equal(jitomate.posicao_na_distribuicao, "acima_do_p75");
});

test("amostra insuficiente e ponto dentro da própria referência", () => {
  // Streaming de películas y música foi criado na cesta 2024: não tem 2010–2019
  assert.equal(executar("analisar_componentes", { operacao: "comparacao_sazonal", serie: "g237", frequencia: "quinzenal" }).status, "amostra_insuficiente");
  assert.equal(executar("analisar_componentes", { operacao: "comparacao_sazonal", serie: "indice_general", frequencia: "mensal", periodo: "2015-09" }).status, "erro_parametro");
});

test("decomposição sem dupla contagem, com total, soma e resíduo (Informe do Banxico, 1ª quinz. ago/26)", () => {
  const servicos = dados(executar("analisar_componentes", { operacao: "decomposicao", pai: "servicios", medida: "contribuicao_no_pai", frequencia: "quinzenal", periodo: "2026-08-Q1" }));
  const partes = Object.fromEntries([...servicos.pressoes_positivas, ...servicos.pressoes_negativas].map((x: any) => [x.id, r2(x.valor)]));
  assert.deepEqual(partes, { otros_servicios: 2.32, vivienda: 1.63, educacion_colegiaturas: 0.39 });
  assert.equal(r2(servicos.total.valor), 4.34);
  assert.ok(Math.abs(servicos.residuo.valor) < 1e-6);
  assert.ok(!("servicios" in partes));
  const mercadorias = dados(executar("analisar_componentes", { operacao: "decomposicao", pai: "mercancias", medida: "contribuicao_no_pai", frequencia: "quinzenal", periodo: "2026-08-Q1" }));
  assert.equal(r2(mercadorias.total.valor), 3.51);
  // incidência no período: núcleo + não núcleo = INPC, resíduo só de arredondamento
  const inpc = dados(executar("analisar_componentes", { operacao: "decomposicao", pai: "indice_general", medida: "incidencia_periodo", frequencia: "quinzenal" }));
  assert.equal(inpc.pressoes_positivas.length + inpc.pressoes_negativas.length, 2);
  assert.ok(Math.abs(inpc.residuo.valor) <= 0.01);
  // genéricos: folhas da árvore, com a linha "demais" em vez de 292 itens
  const genericos = dados(executar("analisar_componentes", { operacao: "decomposicao", pai: "frutas_y_verduras", medida: "incidencia_periodo", nivel_filhos: "genericos", frequencia: "quinzenal" }));
  assert.ok(Math.abs(genericos.residuo.valor) <= 0.01);
});

test("dado ausente, métrica inexistente e fonte externa inexistente", () => {
  const saido = dados(executar("buscar_series", { termo: "Alimentos para bebé" })).candidatos.find((c: any) => c.tipo === "generico_saido");
  assert.ok(saido);
  assert.equal(dados(executar("consultar_dados", { series: [saido.id], metricas: ["variacao_periodo"], frequencia: "mensal" })).series[saido.id].status, "indisponivel");
  const saar = dados(executar("consultar_dados", { series: ["g070"], metricas: ["saar_6m"], frequencia: "mensal" }));
  assert.equal(saar.series.g070.metricas.saar_6m.status, "metrica_indisponivel");
  // expectativa só onde está registrada: 1ª quinz. set/26 e set/26 (Encuesta Citi); nenhuma para ago/26
  const expectativas = dados(executar("consultar_metodologia", { tema: "expectativas" })).expectativas_registradas;
  assert.deepEqual([...new Set(expectativas.map((e: any) => e.periodo))].sort(), ["2026-09", "2026-09-Q1"]);
  assert.ok(expectativas.every((e: any) => e.fonte.includes("Encuesta Citi")));
  const inpc = expectativas.find((e: any) => e.periodo === "2026-09-Q1" && e.indicador === "indice_general");
  assert.equal(r2(inpc.diferenca_pp), 0.05);  // 0,33 − 0,28, como no card "Realizado x expectativa"
});

test("divergência de snapshot, parâmetros inválidos e id inexistente", () => {
  assert.equal(executar("consultar_dados", { series: ["indice_general"], metricas: ["variacao_anual"], frequencia: "mensal", snapshot_id: "outro" }).status, "snapshot_divergente");
  assert.equal(executar("consultar_dados", { series: ["indice_general"], metricas: ["formula_livre"], frequencia: "mensal" }).status, "erro_parametro");
  assert.equal(executar("consultar_dados", { series: ["indice_general"], metricas: ["variacao_anual"], frequencia: "mensal", sql: "drop" }).status, "erro_parametro");
  assert.equal(dados(executar("consultar_dados", { series: ["nao_existe"], metricas: ["variacao_anual"], frequencia: "mensal" })).series.nao_existe.status, "id_inexistente");
  const acao = schemaControlarDashboard(pacote);
  assert.ok(acao.safeParse({ acao: "mostrar", visualizacao: "explorar_frutas_y_verduras_anual", destacar_serie: "g070" }).success);
  assert.ok(!acao.safeParse({ acao: "mostrar", visualizacao: "grafico_que_nao_existe" }).success);
  assert.ok(!acao.safeParse({ acao: "mostrar", visualizacao: "main_top_incidencias", destacar_serie: "g076" }).success);  // tomate verde não está na tabela
  assert.ok(!acao.safeParse({ acao: "mostrar", visualizacao: "grupos_inpc_anual", seletor: "#resumo" }).success);
  assert.ok(!acao.safeParse({ acao: "mostrar", visualizacao: "grupos_inpc_anual", filtro: { inicio: "2022-01" } }).success);
});

test("evidências são estáveis, rastreáveis e apontam para visualizações registradas", () => {
  const a = executar("consultar_dados", { series: ["g070"], metricas: ["incidencia_periodo"], frequencia: "quinzenal" });
  const ev = a.evidencias[0];
  assert.match(ev.id, /^E-[0-9a-f]{6}$/);
  assert.equal(ev.visualizacao, "main_top_incidencias");
  assert.ok(pacote.visualizacoes.some((v) => v.id === ev.visualizacao));
  assert.equal(ev.validacao?.status, "conferido_na_auditoria");
  const ids = new Set(pacote.visualizacoes.map((v) => v.id));
  for (const v of pacote.visualizacoes) for (const s of v.series) assert.ok(pacote.series.some((x) => x.id === s.serie_id), `${v.id}: ${s.serie_id}`);
  assert.equal(ids.size, pacote.visualizacoes.length);
});

test("estimativa do mês vem marcada como estimativa, com a faixa do backtest", () => {
  const r = executar("consultar_metodologia", { tema: "estimativa_do_mes" });
  const estimativa = dados(r).estimativa_do_mes;
  assert.match(estimativa.natureza, /estimado/);
  assert.equal(r2(estimativa.indice_general.mediana_variacao_mensal.valor), 0.42);
  assert.equal(r2(estimativa.indice_general.mediana_variacao_anual.valor), 3.45);
  assert.deepEqual([r2(estimativa.indice_general.p25_variacao_mensal.valor), r2(estimativa.indice_general.p75_variacao_mensal.valor)], [0.37, 0.5]);
  assert.ok(r.evidencias.some((ev) => ev.tipo === "estimado"));
});
