// As seis ferramentas do assistente: cinco de dados, que rodam aqui no servidor sobre o pacote, e controlar_dashboard,
// que só é declarada aqui e roda no navegador. Todo schema é estrito (sem propriedade extra), com enums e limites;
// nenhuma ferramenta aceita código, SQL, seletor, URL ou fórmula. Toda resposta de dados sai no mesmo envelope:
// status, snapshot_id, dados, evidências e limitações. As evidências têm id estável; o texto do modelo cita esses ids.

import { z } from "zod";
import {
  buscar, colunaDaSerie, envelope, metricaDaSerie, evidenciaDerivada, evidenciaExpectativa, evidenciaNumero, evidenciaTrecho, hierarquia, metricasDisponiveis,
  serie, valorEm, type Envelope, type Evidencia, type Frequencia, type Pacote, type Serie,
} from "./pacote.js";

// ==== 1. Vocabulário comum dos schemas ====
const PERIODO = z.string().regex(/^\d{4}-(0[1-9]|1[0-2])(-Q[12])?$/, "período no formato 2026-08 (mês) ou 2026-09-Q1 (quinzena)");
const FREQUENCIA = z.enum(["mensal", "quinzenal"]);
const ID_SERIE = z.string().regex(/^[a-z0-9_]{2,60}$/, "id de série do catálogo (use buscar_series)");
const METRICAS = ["indice", "variacao_periodo", "variacao_anual", "incidencia_periodo", "contribuicao_anual", "contribuicao_no_pai", "contribuicao_no_grupo",
  "norma_mediana", "norma_p25", "norma_p75", "norma_n", "desvio_norma", "desvio_sazonal_ponderado", "variacao_sa_mensal", "saar_3m", "saar_6m",
  "pct_cesta_em_alta", "pct_cesta_anual_acima_3", "cobertura_peso_mes", "cobertura_peso_anual"] as const;
export const TEMAS = ["fontes", "mensal_e_quinzenal", "incidencia", "contribuicao_12_meses", "contribuicao_no_pai", "padrao_sazonal", "desvio_sazonal_ponderado",
  "ajuste_sazonal", "saar", "difusao", "estimativa_do_mes", "expectativas", "cestas_e_genericos", "validacao", "auditoria", "limitacoes", "vocabulario"] as const;
const COMO_CITAR = "Cite cada número do texto com o id da evidência dele entre colchetes logo depois dele, ex.: 0,33% [E-1a2b3c], um id por colchete. Não cite ids que não vieram das ferramentas neste turno.";

export const schemas = {
  consultar_contexto: z.strictObject({}),
  buscar_series: z.strictObject({
    termo: z.string().min(1).max(60).describe("nome ou apelido, em português ou espanhol: 'tomate', 'núcleo', 'Servicios profesionales'"),
    tipo: z.enum(["componente", "generico", "indicador", "todos"]).default("todos"),
    limite: z.number().int().min(1).max(10).default(6),
  }),
  consultar_dados: z.strictObject({
    series: z.array(ID_SERIE).min(1).max(6),
    metricas: z.array(z.enum(METRICAS)).min(1).max(8),
    frequencia: FREQUENCIA,
    inicio: PERIODO.optional(), fim: PERIODO.optional(),
    ultimos: z.number().int().min(1).max(48).optional().describe("os últimos N períodos; sem início e fim, o padrão é 1"),
    snapshot_id: z.string().max(40).optional(),
  }),
  analisar_componentes: z.discriminatedUnion("operacao", [
    z.strictObject({
      operacao: z.literal("ranking"),
      universo: z.enum(["genericos", "filhos"]).describe("genericos: as aberturas (292 itens); filhos: os componentes logo abaixo de 'pai'"),
      pai: ID_SERIE.optional().describe("em genericos, limita aos itens abaixo deste componente; em filhos, é obrigatório"),
      criterio: z.enum(["incidencia_periodo", "variacao_periodo", "desvio_sazonal_ponderado", "variacao_anual", "contribuicao_anual"]),
      direcao: z.enum(["maiores", "menores"]),
      frequencia: FREQUENCIA, periodo: PERIODO.optional(),
      limite: z.number().int().min(1).max(10).default(5),
    }),
    z.strictObject({
      operacao: z.literal("decomposicao"),
      pai: ID_SERIE,
      medida: z.enum(["incidencia_periodo", "contribuicao_anual", "contribuicao_no_pai"])
        .describe("incidencia_periodo: pp da variação do INPC no período; contribuicao_anual: pp da variação em 12 meses do INPC; contribuicao_no_pai: pp da variação em 12 meses do próprio pai"),
      nivel_filhos: z.enum(["componentes", "genericos"]).default("componentes"),
      frequencia: FREQUENCIA, periodo: PERIODO.optional(),
    }),
    z.strictObject({
      operacao: z.literal("comparacao_temporal"),
      serie: ID_SERIE,
      metrica: z.enum(["variacao_anual", "variacao_periodo", "incidencia_periodo", "contribuicao_anual", "saar_6m", "saar_3m"]),
      frequencia: FREQUENCIA, periodo_inicial: PERIODO, periodo_final: PERIODO,
    }),
    z.strictObject({
      operacao: z.literal("comparacao_sazonal"),
      serie: ID_SERIE, frequencia: FREQUENCIA, periodo: PERIODO.optional(),
    }),
    z.strictObject({
      operacao: z.literal("tendencia"),
      series: z.array(z.enum(["indice_general", "subyacente", "no_subyacente", "servicios", "mercancias"])).min(1).max(5).default(["subyacente", "servicios", "mercancias"]),
      meses: z.number().int().min(3).max(24).default(6).describe("quantos meses para trás, no mensal"),
    }),
    z.strictObject({
      operacao: z.literal("exclusao_contabil"),
      excluir: z.array(ID_SERIE).min(1).max(5).describe("componentes ou genéricos cuja contribuição no período sai da conta"),
      frequencia: FREQUENCIA, periodo: PERIODO.optional(),
    }),
  ]),
  consultar_metodologia: z.strictObject({
    tema: z.enum(TEMAS),
    termo: z.string().max(40).optional().describe("palavra para filtrar os trechos do tema"),
  }),
};

// ==== 2. Contexto do pedido ====
export type EstadoTela = { aba: string; visualizacao_em_foco: string | null; destaque: string | null; revisao: number };
export type Contexto = { pacote: Pacote; estado: EstadoTela; acompanhar: boolean };

const limitacoesGerais = (pacote: Pacote) => [
  "As figuras não têm filtro de período nem janela ajustável: o assistente abre, rola e destaca, mas não recorta.",
  "O ajuste sazonal (variação dessazonalizada e SAAR) é um STL do projeto, não série oficial do INEGI, e a ponta revisa.",
  `Os genéricos têm só os últimos ${pacote.parametros.meses_de_genericos} meses no pacote; incidência de genérico só existe na cesta 2024.`,
  "Expectativa de mercado só existe onde está registrada (entrada manual com fonte e data, ou Pesquisa do Banxico). Não há consenso Bloomberg.",
  "Esta versão é um retrato do release no snapshot; a atualização automática só roda na main.",
];

// ==== 3. consultar_contexto ====
function consultarContexto(c: Contexto): Envelope {
  const { pacote } = c;
  const foco = pacote.visualizacoes.find((v) => v.id === c.estado.visualizacao_em_foco);
  const dados = {
    snapshot_id: pacote.snapshot_id, gerado_em: pacote.gerado_em, versao_metodologia: pacote.metodologia.versao,
    release: pacote.release,
    estado_tela: { ...c.estado, titulo_em_foco: foco?.titulo ?? null, series_em_foco: foco?.series.map((s) => s.serie_id) ?? [] },
    acompanhar_no_dashboard: c.acompanhar,
    cobertura: { componentes: "16 componentes, mensal e quinzenal, desde 2000", genericos: `292 genéricos, últimos ${pacote.parametros.meses_de_genericos} meses`,
                 padrao_sazonal: `mediana, p25 e p75 de ${pacote.parametros.anos_padrao_sazonal.join("–")}` },
    expectativas_registradas: pacote.expectativas.map((e) => ({ periodo: e.periodo, indicador: e.indicador, fonte: e.fonte })),
    validacao: pacote.validacao,
    visualizacoes: pacote.visualizacoes.map((v) => ({ id: v.id, titulo: v.titulo, abas: v.abas, frequencia: v.frequencia, metricas: v.metricas,
      series: v.series.map((s) => s.serie_id), destaques_suportados: v.destaques_suportados })),
    como_citar: COMO_CITAR,
  };
  return envelope(pacote, "ok", dados, [], limitacoesGerais(pacote));
}

// ==== 4. buscar_series ====
function buscarSeries(c: Contexto, e: z.infer<typeof schemas.buscar_series>): Envelope {
  const { pacote } = c;
  const tipos = e.tipo === "todos" ? null : e.tipo === "generico" ? ["generico", "generico_saido"] : [e.tipo];
  const achados = buscar(pacote, e.termo).filter((a) => !tipos || tipos.includes(a.serie.tipo)).slice(0, e.limite);
  const exatas = achados.filter((a) => a.correspondencia === "exata");
  const candidatos = achados.map((a) => ({
    id: a.serie.id, nome_oficial: a.serie.nome_oficial, nome_exibicao: a.serie.nome_exibicao, aliases: a.serie.aliases, tipo: a.serie.tipo,
    correspondencia: a.correspondencia, nome_que_casou: a.nome_que_casou, hierarquia: hierarquia(pacote, a.serie.id).join(" > "),
    cobertura: a.serie.cobertura, cestas: a.serie.cestas, peso_cesta_2024: a.serie.peso_cesta_2024 ?? null,
    metricas: metricasDisponiveis(pacote, a.serie.id),
  }));
  // a regra de decisão fica explícita: uma exata, resolvido; mais de uma, ambíguo; nenhuma, só candidatos de baixa confiança
  const status = achados.length === 0 ? "indisponivel" : exatas.length === 1 ? "ok" : exatas.length > 1 ? "ambiguo" : "baixa_confianca";
  const orientacao = {
    ok: `Resolvido: ${exatas[0]?.serie.id}. Os demais candidatos são só relacionados.`,
    ambiguo: `O termo corresponde exatamente a ${exatas.length} séries (${exatas.map((a) => a.serie.nome_oficial).join(", ")}). Pergunte ao usuário qual delas; não escolha sozinho.`,
    baixa_confianca: "Nenhuma correspondência exata. Não escolha um candidato por conta própria: mostre as opções e pergunte.",
    indisponivel: "Nada no catálogo com esse nome. Diga que a série não existe no pacote; não substitua por outra.",
  }[status];
  return envelope(pacote, status, { termo: e.termo, orientacao, candidatos, como_citar: COMO_CITAR });
}

// ==== 5. consultar_dados ====
function periodosPedidos<T extends { periodo: string }>(pontos: T[], e: { inicio?: string; fim?: string; ultimos?: number }) {
  if (e.inicio || e.fim) return pontos.filter((p) => (!e.inicio || p.periodo >= e.inicio) && (!e.fim || p.periodo <= e.fim));
  return pontos.slice(-(e.ultimos ?? 1));
}

function consultarDados(c: Contexto, e: z.infer<typeof schemas.consultar_dados>): Envelope {
  const { pacote } = c;
  if (e.snapshot_id && e.snapshot_id !== pacote.snapshot_id)
    return envelope(pacote, "snapshot_divergente", { pedido: e.snapshot_id, servidor: pacote.snapshot_id }, [], ["O snapshot pedido não é o do servidor; nenhum número foi consultado."]);
  const resultado: Record<string, unknown> = {};
  const evidencias: Evidencia[] = [];
  const limitacoes = new Set<string>();
  let algumValor = false;
  for (const id of e.series) {
    const s = serie(pacote, id);
    if (!s) { resultado[id] = { status: "id_inexistente", orientacao: "Use buscar_series para achar o id." }; continue; }
    if (s.tipo === "generico_saido") {
      resultado[id] = { status: "indisponivel", motivo: "item da cesta 2018 que saiu da cesta 2024; o pacote não tem série dele", cestas: s.cestas };
      continue;
    }
    const porMetrica: Record<string, unknown> = {};
    for (const metrica of e.metricas) {
      const pontos = colunaDaSerie(pacote, id, e.frequencia, metrica);
      if (!pontos) { porMetrica[metrica] = { status: "metrica_indisponivel", disponiveis: metricasDisponiveis(pacote, id) }; continue; }
      // uma resposta leva até 48 períodos; num intervalo maior ficam os mais recentes, e o corte precisa ser dito
      const noIntervalo = periodosPedidos(pontos, e);
      const escolhidos = noIntervalo.slice(-48);
      if (noIntervalo.length > 48)
        limitacoes.add(`${metrica}: o intervalo pedido tem ${noIntervalo.length} períodos e vieram só os 48 mais recentes, a partir de ${escolhidos[0].rotulo}; diga isso ao falar do começo do intervalo.`);
      if (!escolhidos.length) { porMetrica[metrica] = { status: "fora_da_cobertura", cobertura: s.cobertura[e.frequencia] ?? null }; continue; }
      const m = metricaDaSerie(pacote, s, metrica);
      const ausentes = escolhidos.filter((p) => p.valor === null).map((p) => p.periodo);
      // evidência para cada ponto quando são poucos; numa série longa, para o primeiro e o último, que é o que se cita
      const comEvidencia = escolhidos.length <= 4 ? escolhidos : [escolhidos[0], escolhidos[escolhidos.length - 1]];
      const ids = new Map(comEvidencia.filter((p) => p.valor !== null).map((p) => {
        const ev = evidenciaNumero(pacote, s, metrica, e.frequencia, p.periodo, p.rotulo, p.valor);
        evidencias.push(ev);
        return [p.periodo, ev.id];
      }));
      algumValor ||= escolhidos.some((p) => p.valor !== null);
      porMetrica[metrica] = {
        status: ausentes.length ? "parcial" : "ok", unidade: m.unidade, natureza: m.natureza, validacao: m.validacao.status,
        valores: escolhidos.map((p) => ({ periodo: p.periodo, rotulo: p.rotulo, valor: p.valor, evidencia: ids.get(p.periodo) ?? null })),
        // ausente é ausente: nunca vira zero
        ausentes,
      };
      if (m.validacao.status === "reprovado") limitacoes.add(`${metrica}: validação reprovada; não sustenta conclusão.`);
      if (m.limitacao) limitacoes.add(`${metrica}: ${m.limitacao}.`);
    }
    if (s.tipo === "generico" && !s.cestas.includes("2018")) limitacoes.add(`${s.nome_oficial}: criado na cesta 2024, sem histórico antes de jul/2024 nem padrão sazonal.`);
    resultado[id] = { status: "ok", nome: s.nome_exibicao, nome_oficial: s.nome_oficial, hierarquia: hierarquia(pacote, id).join(" > "), metricas: porMetrica };
  }
  return envelope(pacote, algumValor ? "ok" : "indisponivel", { frequencia: e.frequencia, series: resultado, como_citar: COMO_CITAR }, evidencias, [...limitacoes]);
}

// ==== 6. analisar_componentes ====
type Analise = z.infer<typeof schemas.analisar_componentes>;
const periodoPadrao = (pacote: Pacote, f: Frequencia, periodo?: string) => periodo ?? pacote.release.ultimo_periodo[f];

function descendentesGenericos(pacote: Pacote, pai: string): Serie[] {
  // os genéricos abaixo de um componente, descendo a árvore; são folhas, então nunca conto um nível duas vezes
  const abaixo = new Set([pai]);
  let mudou = true;
  while (mudou) {
    mudou = false;
    for (const s of pacote.series) if (s.pai && abaixo.has(s.pai) && !abaixo.has(s.id) && s.tipo === "componente") { abaixo.add(s.id); mudou = true; }
  }
  return pacote.series.filter((s) => s.tipo === "generico" && s.pai && abaixo.has(s.pai));
}

function ranking(c: Contexto, a: Extract<Analise, { operacao: "ranking" }>): Envelope {
  const { pacote } = c;
  const periodo = periodoPadrao(pacote, a.frequencia, a.periodo);
  if (a.universo === "filhos" && !a.pai) return envelope(pacote, "erro_parametro", { erro: "universo 'filhos' exige 'pai'" });
  const pai = a.pai ? serie(pacote, a.pai) : undefined;
  if (a.pai && !pai) return envelope(pacote, "erro_parametro", { erro: `id inexistente: ${a.pai}` });
  const universo = a.universo === "filhos" ? pai!.filhos.map((id) => serie(pacote, id)!) : pai ? descendentesGenericos(pacote, pai.id) : pacote.series.filter((s) => s.tipo === "generico");
  if (!universo.length) return envelope(pacote, "erro_parametro", { erro: `${a.pai} não tem filhos componentes; use universo 'genericos'` });
  const itens = universo.map((s) => ({ s, ponto: valorEm(pacote, s.id, a.frequencia, a.criterio, periodo) })).filter((x) => x.ponto?.valor != null);
  if (!itens.length) return envelope(pacote, "indisponivel", { periodo, criterio: a.criterio, motivo: "nenhum item tem essa métrica nesse período e frequência" });
  itens.sort((x, y) => (a.direcao === "maiores" ? y.ponto!.valor! - x.ponto!.valor! : x.ponto!.valor! - y.ponto!.valor!));
  const evidencias: Evidencia[] = [];
  const lista = itens.slice(0, a.limite).map(({ s, ponto }, i) => {
    const ev = evidenciaNumero(pacote, s, a.criterio, a.frequencia, periodo, ponto!.rotulo, ponto!.valor);
    evidencias.push(ev);
    // a outra medida ao lado, para o leitor ver que variação alta com peso pequeno não é contribuição alta
    const outra = a.criterio === "incidencia_periodo" ? "variacao_periodo" : a.criterio === "variacao_periodo" ? "incidencia_periodo" : null;
    const complemento = outra ? valorEm(pacote, s.id, a.frequencia, outra, periodo) : null;
    if (outra && complemento?.valor != null) evidencias.push(evidenciaNumero(pacote, s, outra, a.frequencia, periodo, complemento.rotulo, complemento.valor));
    return { posicao: i + 1, id: s.id, nome: s.nome_exibicao, grupo: s.pai ? serie(pacote, s.pai)?.nome_exibicao : null, valor: ponto!.valor, evidencia: ev.id,
             ...(outra ? { [outra]: complemento?.valor ?? null } : {}), peso_cesta_2024: s.peso_cesta_2024 ?? null };
  });
  const m = pacote.metricas[a.criterio];
  return envelope(pacote, "ok", {
    operacao: "ranking", criterio: a.criterio, criterio_nome: m.nome, unidade: m.unidade, direcao: a.direcao, periodo, frequencia: a.frequencia,
    universo: a.universo, pai: a.pai ?? null, itens_considerados: itens.length, lista, como_citar: COMO_CITAR,
  }, evidencias, a.criterio === "variacao_periodo" ? ["Ranking por variação ignora o peso: itens pequenos com alta grande sobem na lista. Para o que puxou o índice, use incidencia_periodo."] : []);
}

function decomposicao(c: Contexto, a: Extract<Analise, { operacao: "decomposicao" }>): Envelope {
  const { pacote } = c;
  const pai = serie(pacote, a.pai);
  if (!pai || pai.tipo !== "componente") return envelope(pacote, "erro_parametro", { erro: `pai precisa ser um dos 16 componentes; recebi ${a.pai}` });
  const periodo = periodoPadrao(pacote, a.frequencia, a.periodo);
  const genericos = a.nivel_filhos === "genericos";
  if (genericos && a.medida !== "incidencia_periodo")
    return envelope(pacote, "erro_parametro", { erro: "nos genéricos só a incidência do período soma o pai; use medida incidencia_periodo" });
  const filhos = genericos ? descendentesGenericos(pacote, pai.id) : pai.filhos.map((id) => serie(pacote, id)!);
  if (!filhos.length) return envelope(pacote, "erro_parametro", { erro: `${pai.id} não tem componentes abaixo; use nivel_filhos 'genericos'` });
  // o total de referência de cada medida: a incidência publicada do pai, a contribuição anual dele, ou a variação em 12 meses dele;
  // no INPC o total é a própria variação, em %, que as contribuições em pp somam
  const metricaTotal = a.medida === "contribuicao_no_pai" ? "variacao_anual"
    : pai.id === "indice_general" ? (a.medida === "incidencia_periodo" ? "variacao_periodo" : "variacao_anual") : a.medida;
  const total = valorEm(pacote, pai.id, a.frequencia, metricaTotal, periodo);
  if (!total || total.valor == null) return envelope(pacote, "indisponivel", { periodo, motivo: `${pai.nome_exibicao} não tem ${metricaTotal} nesse período` });
  const partes = filhos.map((s) => ({ s, ponto: valorEm(pacote, s.id, a.frequencia, a.medida, periodo) }));
  const semDado = partes.filter((x) => x.ponto?.valor == null).map((x) => x.s.nome_exibicao);
  const validas = partes.filter((x) => x.ponto?.valor != null).sort((x, y) => y.ponto!.valor! - x.ponto!.valor!);
  // a única conta do servidor: somar as partes já exportadas e subtrair do total (resíduo de arredondamento e cobertura)
  const soma = validas.reduce((t, x) => t + x.ponto!.valor!, 0);
  const evidencias = [evidenciaNumero(pacote, pai, metricaTotal, a.frequencia, periodo, total.rotulo, total.valor)];
  const linha = ({ s, ponto }: typeof validas[number]) => {
    const ev = evidenciaNumero(pacote, s, a.medida, a.frequencia, periodo, ponto!.rotulo, ponto!.valor);
    evidencias.push(ev);
    return { id: s.id, nome: s.nome_exibicao, valor: ponto!.valor, evidencia: ev.id };
  };
  // com 292 genéricos, mostro os 8 de cada lado e junto o resto numa linha só, com a soma
  const positivas = validas.filter((x) => x.ponto!.valor! > 0), negativas = validas.filter((x) => x.ponto!.valor! < 0).reverse();
  const corte = genericos ? 8 : Infinity;
  const resto = [...positivas.slice(corte), ...negativas.slice(corte)];
  const m = pacote.metricas[a.medida];
  const chave = `${pai.id}|${a.medida}|${a.nivel_filhos}|${a.frequencia}|${periodo}`;
  const evSoma = evidenciaDerivada(pacote, `soma|${chave}`, "derivado", `soma das partes de ${pai.nome_exibicao}, ${total.rotulo}`, soma, m.unidade, "soma de valores do pacote");
  const evResiduo = evidenciaDerivada(pacote, `residuo|${chave}`, "derivado", `resíduo (total − soma das partes), ${total.rotulo}`, total.valor - soma, m.unidade, "subtração de valores do pacote");
  evidencias.push(evSoma, evResiduo);
  return envelope(pacote, "ok", {
    operacao: "decomposicao", pai: pai.id, pai_nome: pai.nome_exibicao, medida: a.medida, medida_nome: m.nome, unidade: m.unidade, periodo,
    rotulo_periodo: total.rotulo, frequencia: a.frequencia, nivel: genericos ? "genéricos abaixo do pai (folhas da árvore)" : "filhos diretos do pai",
    total: { metrica: metricaTotal, valor: total.valor, evidencia: evidencias[0].id },
    pressoes_positivas: positivas.slice(0, corte).map(linha), pressoes_negativas: negativas.slice(0, corte).map(linha),
    demais: resto.length ? { itens: resto.length, soma: resto.reduce((t, x) => t + x.ponto!.valor!, 0) } : null,
    soma_das_partes: { valor: soma, evidencia: evSoma.id }, residuo: { valor: total.valor - soma, evidencia: evResiduo.id }, sem_dado: semDado, como_citar: COMO_CITAR,
  }, evidencias, [
    "Decomposição contábil: diz de onde veio a variação, não por quê. Não há evidência causal no pacote.",
    "O resíduo é arredondamento das incidências publicadas (3 casas) ou itens sem dado; o pai não entra na soma dos próprios filhos.",
    ...(genericos ? ["A soma das incidências dos genéricos difere da incidência publicada do pai na 4ª casa (peso efetivo do projeto vs cálculo interno do INEGI)."] : []),
  ]);
}

function comparacaoTemporal(c: Contexto, a: Extract<Analise, { operacao: "comparacao_temporal" }>): Envelope {
  const { pacote } = c;
  const s = serie(pacote, a.serie);
  if (!s) return envelope(pacote, "erro_parametro", { erro: `id inexistente: ${a.serie}` });
  const inicial = valorEm(pacote, s.id, a.frequencia, a.metrica, a.periodo_inicial), final = valorEm(pacote, s.id, a.frequencia, a.metrica, a.periodo_final);
  if (inicial?.valor == null || final?.valor == null)
    return envelope(pacote, "indisponivel", { motivo: "falta valor em um dos períodos", cobertura: s.cobertura[a.frequencia] ?? null, inicial: inicial?.valor ?? null, final: final?.valor ?? null });
  const m = pacote.metricas[a.metrica];
  const evidencias = [evidenciaNumero(pacote, s, a.metrica, a.frequencia, a.periodo_inicial, inicial.rotulo, inicial.valor),
                      evidenciaNumero(pacote, s, a.metrica, a.frequencia, a.periodo_final, final.rotulo, final.valor)];
  const diferenca = final.valor - inicial.valor;
  const evDiferenca = evidenciaDerivada(pacote, `${s.id}|${a.metrica}|${a.frequencia}|${a.periodo_inicial}|${a.periodo_final}`, "derivado",
    `${s.nome_exibicao}: ${m.unidade === "%" ? "mudança da taxa" : "diferença"} de ${inicial.rotulo} para ${final.rotulo}`, diferenca, "pp", "subtração de dois valores do pacote");
  evidencias.push(evDiferenca);
  const variacaoNoFinal = valorEm(pacote, s.id, a.frequencia, "variacao_periodo", a.periodo_final);
  if (variacaoNoFinal?.valor != null) evidencias.push(evidenciaNumero(pacote, s, "variacao_periodo", a.frequencia, a.periodo_final, variacaoNoFinal.rotulo, variacaoNoFinal.valor));
  return envelope(pacote, "ok", {
    operacao: "comparacao_temporal", serie: s.id, nome: s.nome_exibicao, metrica: a.metrica, metrica_nome: m.nome, frequencia: a.frequencia,
    inicial: { periodo: a.periodo_inicial, rotulo: inicial.rotulo, valor: inicial.valor, evidencia: evidencias[0].id },
    final: { periodo: a.periodo_final, rotulo: final.rotulo, valor: final.valor, evidencia: evidencias[1].id },
    // diferença entre duas taxas exportadas, a mesma conta do cartão do dashboard; não é a variação do índice entre as datas
    mudanca_da_taxa_pp: m.unidade === "%" ? evDiferenca.valor : null, diferenca_pp: m.unidade === "pp" ? evDiferenca.valor : null, evidencia_da_diferenca: evDiferenca.id,
    variacao_do_indice_no_periodo_final: variacaoNoFinal?.valor ?? null, como_citar: COMO_CITAR,
  }, evidencias, ["mudanca_da_taxa_pp é a diferença entre duas taxas, em pontos percentuais; não é a variação do índice entre os dois períodos. Taxa menor não é queda de preços."]);
}

function comparacaoSazonal(c: Contexto, a: Extract<Analise, { operacao: "comparacao_sazonal" }>): Envelope {
  const { pacote } = c;
  const s = serie(pacote, a.serie);
  if (!s) return envelope(pacote, "erro_parametro", { erro: `id inexistente: ${a.serie}` });
  const periodo = periodoPadrao(pacote, a.frequencia, a.periodo);
  const [inicio, fim] = pacote.parametros.anos_padrao_sazonal;
  const ano = Number(periodo.slice(0, 4));
  // o ponto analisado não pode estar na própria referência histórica
  if (ano >= inicio && ano <= fim)
    return envelope(pacote, "erro_parametro", { erro: `o período ${periodo} está dentro da janela do padrão sazonal (${inicio}–${fim}); a comparação não é válida` });
  const pegar = (m: string) => valorEm(pacote, s.id, a.frequencia, m, periodo);
  const observado = pegar("variacao_periodo");
  if (observado?.valor == null) return envelope(pacote, "indisponivel", { periodo, motivo: "sem variação observada nesse período e frequência", cobertura: s.cobertura[a.frequencia] ?? null });
  const [mediana, p25, p75, n] = ["norma_mediana", "norma_p25", "norma_p75", "norma_n"].map(pegar);
  const posicaoNoAno = a.frequencia === "quinzenal" ? `${periodo.slice(5, 7)}-${periodo.slice(8)}` : periodo.slice(5, 7);
  const base = { operacao: "comparacao_sazonal", serie: s.id, nome: s.nome_exibicao, frequencia: a.frequencia, periodo, rotulo_periodo: observado.rotulo,
                 posicao_no_ano: posicaoNoAno, janela_referencia: `${inicio}–${fim}`, observado: observado.valor };
  const evidencias = [evidenciaNumero(pacote, s, "variacao_periodo", a.frequencia, periodo, observado.rotulo, observado.valor)];
  const amostra = n?.valor ?? 0;
  if (mediana?.valor == null || amostra < pacote.parametros.minimo_anos_padrao_sazonal)
    return envelope(pacote, "amostra_insuficiente", { ...base, n: amostra, minimo: pacote.parametros.minimo_anos_padrao_sazonal,
      orientacao: "Sem histórico suficiente no mesmo período do ano; não classifique como normal ou anormal." }, evidencias,
      [`${s.nome_oficial} tem ${amostra} ano(s) de ${inicio}–${fim} nessa posição do ano.`]);
  for (const [m, p] of [["norma_mediana", mediana], ["norma_p25", p25], ["norma_p75", p75], ["norma_n", n]] as const)
    evidencias.push(evidenciaNumero(pacote, s, m, a.frequencia, periodo, p!.rotulo, p!.valor));
  const faixa = observado.valor > p75!.valor! ? "acima_do_p75" : observado.valor < p25!.valor! ? "abaixo_do_p25" : "entre_p25_e_p75";
  const desvio = pegar("desvio_norma");
  if (desvio?.valor != null) evidencias.push(evidenciaNumero(pacote, s, "desvio_norma", a.frequencia, periodo, desvio.rotulo, desvio.valor));
  return envelope(pacote, "ok", {
    ...base, mediana: mediana.valor, p25: p25!.valor, p75: p75!.valor, n: amostra, posicao_na_distribuicao: faixa, desvio_da_mediana_pp: desvio?.valor ?? null,
    evidencias_por_campo: Object.fromEntries(evidencias.map((ev) => [ev.metrica!, ev.id])), como_citar: COMO_CITAR,
  }, evidencias, [
    "É desvio em relação ao padrão sazonal de 2010–2019, não surpresa contra expectativa de mercado.",
    "A faixa p25–p75 contém metade dos anos da janela; fora dela não prova anomalia com n pequeno.",
  ]);
}

function tendencia(c: Contexto, a: Extract<Analise, { operacao: "tendencia" }>): Envelope {
  // só o que o pipeline já calculou, lado a lado e sem nota nem índice composto: 12 meses, SAAR e variação
  // dessazonalizada no mensal, e a difusão. A leitura fica com o economista
  const { pacote } = c;
  const evidencias: Evidencia[] = [];
  const janela = (id: string, metrica: string) => (colunaDaSerie(pacote, id, "mensal", metrica) ?? []).filter((p) => p.valor != null).slice(-a.meses);
  const comEvidencias = (s: Serie, metrica: string) => {
    const pontos = janela(s.id, metrica);
    if (!pontos.length) return null;
    const pontas = [pontos[0], pontos[pontos.length - 1]].map((p) => evidenciaNumero(pacote, s, metrica, "mensal", p.periodo, p.rotulo, p.valor));
    evidencias.push(...pontas);
    return { unidade: pacote.metricas[metrica].unidade, valores: pontos.map((p) => ({ periodo: p.periodo, rotulo: p.rotulo, valor: p.valor })),
             evidencia_inicio: pontas[0].id, evidencia_fim: pontas[1].id };
  };
  const series = Object.fromEntries(a.series.map((id) => {
    const s = serie(pacote, id)!;
    return [id, { nome: s.nome_exibicao, variacao_anual: comEvidencias(s, "variacao_anual"), saar_6m: comEvidencias(s, "saar_6m"),
                  saar_3m: comEvidencias(s, "saar_3m"), variacao_sa_mensal: comEvidencias(s, "variacao_sa_mensal") }];
  }));
  const difusao = serie(pacote, "difusao")!;
  return envelope(pacote, "ok", {
    operacao: "tendencia", frequencia: "mensal", meses: a.meses, series,
    difusao: { pct_cesta_em_alta: comEvidencias(difusao, "pct_cesta_em_alta"), pct_cesta_anual_acima_3: comEvidencias(difusao, "pct_cesta_anual_acima_3") },
    ultima_quinzena: `a tendência é mensal (até ${pacote.release.ultimo_rotulo.mensal}); a quinzena de ${pacote.release.ultimo_rotulo.quinzenal} não é dessazonalizada`,
    como_citar: COMO_CITAR,
  }, evidencias, [
    "SAAR e variação dessazonalizada vêm do STL do projeto, não do INEGI; a ponta revisa quando entra um mês novo (SAAR 6m do núcleo: 1,00 pp em média).",
    "A taxa em 12 meses mais baixa não prova melhora subjacente; compare com o SAAR e a difusão, sabendo que nenhuma medida sozinha decide.",
  ]);
}

function exclusaoContabil(c: Contexto, a: Extract<Analise, { operacao: "exclusao_contabil" }>): Envelope {
  // a variação observada do INPC no período menos as contribuições (incidências) retiradas. Soma e subtração de
  // valores exportados, e nada mais: não é índice reponderado nem previsão
  const { pacote } = c;
  const periodo = periodoPadrao(pacote, a.frequencia, a.periodo);
  const itens = a.excluir.map((id) => serie(pacote, id));
  const inexistente = a.excluir.find((id, i) => !itens[i] || itens[i]!.tipo === "generico_saido" || itens[i]!.tipo === "indicador");
  if (inexistente) return envelope(pacote, "erro_parametro", { erro: `não dá para excluir ${inexistente}: não é componente nem genérico com série` });
  if (a.excluir.includes("indice_general")) return envelope(pacote, "erro_parametro", { erro: "o INPC não pode ser excluído dele mesmo" });
  // um item e um ancestral dele contariam a mesma contribuição duas vezes
  for (const s of itens) {
    let pai = s!.pai;
    while (pai) {
      if (a.excluir.includes(pai)) return envelope(pacote, "erro_parametro", { erro: `${s!.id} já está dentro de ${pai}; excluir os dois contaria duas vezes` });
      pai = serie(pacote, pai)?.pai ?? null;
    }
  }
  const inpc = serie(pacote, "indice_general")!;
  const observado = valorEm(pacote, inpc.id, a.frequencia, "variacao_periodo", periodo);
  if (observado?.valor == null) return envelope(pacote, "indisponivel", { periodo, motivo: "sem variação do INPC nesse período" });
  const partes = itens.map((s) => ({ s: s!, ponto: valorEm(pacote, s!.id, a.frequencia, "incidencia_periodo", periodo) }));
  const semDado = partes.filter((x) => x.ponto?.valor == null).map((x) => x.s.id);
  if (semDado.length) return envelope(pacote, "indisponivel", { periodo, motivo: `sem contribuição no período para ${semDado.join(", ")}` });
  const evidencias = [evidenciaNumero(pacote, inpc, "variacao_periodo", a.frequencia, periodo, observado.rotulo, observado.valor)];
  const retiradas = partes.map(({ s, ponto }) => {
    const ev = evidenciaNumero(pacote, s, "incidencia_periodo", a.frequencia, periodo, ponto!.rotulo, ponto!.valor);
    evidencias.push(ev);
    return { id: s.id, nome: s.nome_exibicao, contribuicao_pp: ponto!.valor, evidencia: ev.id };
  });
  const soma = retiradas.reduce((t, x) => t + x.contribuicao_pp!, 0);
  const resultado = evidenciaDerivada(pacote, `exclusao|${a.frequencia}|${periodo}|${[...a.excluir].sort().join(",")}`, "derivado",
    `INPC ${observado.rotulo} menos a contribuição de ${retiradas.map((x) => x.nome).join(", ")} (exclusão contábil)`, observado.valor - soma, "%",
    "subtração de valores do pacote: variação observada menos incidências");
  evidencias.push(resultado);
  return envelope(pacote, "ok", {
    operacao: "exclusao_contabil", periodo, rotulo_periodo: observado.rotulo, frequencia: a.frequencia,
    inpc_observado: { valor: observado.valor, unidade: "%", evidencia: evidencias[0].id },
    retiradas, soma_retirada_pp: soma, resultado: { valor: resultado.valor, unidade: "%", evidencia: resultado.id },
    hipotese: "conta o que sobraria da variação do período se os itens retirados tivessem contribuído zero, com os demais iguais",
    como_citar: COMO_CITAR,
  }, evidencias, [
    "Exclusão contábil: não é índice reponderado (os pesos dos outros itens não foram redistribuídos) nem previsão.",
    "Não diz o que teria acontecido sem o choque: os preços dos outros itens podem depender dele.",
    ...(a.frequencia === "quinzenal" ? ["Vale para a quinzena; a variação em 12 meses sem o item exigiria encadear a conta período a período, o que esta ferramenta não faz."] : []),
  ]);
}

function analisarComponentes(c: Contexto, a: Analise): Envelope {
  switch (a.operacao) {
    case "ranking": return ranking(c, a);
    case "decomposicao": return decomposicao(c, a);
    case "comparacao_temporal": return comparacaoTemporal(c, a);
    case "comparacao_sazonal": return comparacaoSazonal(c, a);
    case "tendencia": return tendencia(c, a);
    case "exclusao_contabil": return exclusaoContabil(c, a);
  }
}

// ==== 7. consultar_metodologia ====
function consultarMetodologia(c: Contexto, e: z.infer<typeof schemas.consultar_metodologia>): Envelope {
  const { pacote } = c;
  const porId = new Map(pacote.metodologia.trechos.map((t) => [t.id, t]));
  const doTema = (pacote.metodologia.temas[e.tema] ?? []).map((id) => porId.get(id)!).filter(Boolean);
  const filtrados = e.termo ? doTema.filter((t) => t.texto.toLowerCase().includes(e.termo!.toLowerCase())) : doTema;
  const trechos = filtrados.length ? filtrados : doTema;
  const evidencias = trechos.map((t) => evidenciaTrecho(pacote, t));
  const extras = e.tema === "expectativas" ? expectativasRegistradas(pacote) : e.tema === "estimativa_do_mes" ? estimativaDoMes(pacote) : { dados: {}, evidencias: [] };
  return envelope(pacote, "ok", {
    tema: e.tema, versao_metodologia: pacote.metodologia.versao,
    trechos: trechos.map((t, i) => ({ evidencia: evidencias[i].id, arquivo: t.arquivo, secao: t.secao, texto: t.texto })),
    ...extras.dados, como_citar: COMO_CITAR,
  }, [...evidencias, ...extras.evidencias], e.termo && !filtrados.length ? [`Nenhum trecho do tema menciona "${e.termo}"; devolvi o tema inteiro.`] : []);
}

function expectativasRegistradas(pacote: Pacote) {
  // o realizado contra o esperado usa os dois números arredondados em 2 casas, a mesma conta do card "Realizado x expectativa"
  const evidencias: Evidencia[] = [];
  const lista = pacote.expectativas.map((x) => {
    const ev = evidenciaExpectativa(pacote, x);
    evidencias.push(ev);
    if (x.realizado == null) return { ...x, evidencia: ev.id, diferenca_pp: null };
    const s = serie(pacote, x.indicador)!;
    const realizado = evidenciaNumero(pacote, s, "variacao_periodo", pacote.release.frequencia_do_release, x.periodo, x.rotulo_periodo, x.realizado);
    const diferenca = Math.round(x.realizado * 100) / 100 - Math.round(x.esperado * 100) / 100;
    const evDiferenca = evidenciaDerivada(pacote, `surpresa|${x.periodo}|${x.indicador}`, "derivado", `${s.nome_exibicao}: realizado − esperado, ${x.rotulo_periodo} (${x.fonte})`,
                                          diferenca, "pp", `subtração dos valores arredondados; expectativa: ${x.fonte}`);
    evidencias.push(realizado, evDiferenca);
    return { ...x, evidencia: ev.id, evidencia_realizado: realizado.id, diferenca_pp: evDiferenca.valor, evidencia_diferenca: evDiferenca.id };
  });
  return { dados: { expectativas_registradas: lista, periodos_sem_expectativa: "qualquer período fora desta lista não tem expectativa registrada" }, evidencias };
}

function estimativaDoMes(pacote: Pacote) {
  // a estimativa do pipeline para o mês que ainda não fechou; só existe no dia da 1ª quinzena
  const estimativa = pacote.estimativa_do_mes;
  if (!estimativa) return { dados: { estimativa_do_mes: null, motivo: "o release atual é mensal; não há mês em aberto" }, evidencias: [] as Evidencia[] };
  const evidencias: Evidencia[] = [];
  const dados: Record<string, unknown> = { mes: estimativa.mes, rotulo_mes: estimativa.rotulo_mes };
  for (const indicador of ["indice_general", "subyacente"]) {
    const item = estimativa[indicador];
    const nome = serie(pacote, indicador)!.nome_exibicao;
    const campos: Record<string, unknown> = { cobertura_da_faixa_pct: item.cobertura_da_faixa, meses_testados: item.meses_testados };
    for (const cenario of ["p25", "mediana", "p75"]) for (const medida of ["variacao_mensal", "variacao_anual"]) {
      const ev = evidenciaDerivada(pacote, `estimativa|${indicador}|${cenario}|${medida}`, "estimado",
        `${nome}: estimativa para ${estimativa.rotulo_mes}, ${cenario === "mediana" ? "central" : cenario}, ${medida === "variacao_mensal" ? "no mês" : "em 12 meses"}`,
        item[cenario][medida], "%", "estimativa do pipeline (1ª quinzena publicada e 2ª pela mediana sazonal)");
      evidencias.push(ev);
      campos[`${cenario}_${medida}`] = { valor: item[cenario][medida], evidencia: ev.id };
    }
    const evCobertura = evidenciaDerivada(pacote, `estimativa|${indicador}|cobertura`, "derivado", `${nome}: cobertura da faixa fora da amostra`,
                                          item.cobertura_da_faixa, "%", `backtest do pipeline, ${item.meses_testados} meses`);
    evidencias.push(evCobertura);
    campos.evidencia_cobertura = evCobertura.id;
    dados[indicador] = campos;
  }
  return { dados: { estimativa_do_mes: { ...dados, natureza: "estimado: não é dado publicado nem expectativa de mercado" } }, evidencias };
}

// ==== 8. Execução com validação e cache ====
export const FERRAMENTAS_DE_DADOS = ["consultar_contexto", "buscar_series", "consultar_dados", "analisar_componentes", "consultar_metodologia"] as const;
export type FerramentaDeDados = (typeof FERRAMENTAS_DE_DADOS)[number];
const executores: Record<FerramentaDeDados, (c: Contexto, e: any) => Envelope> = {
  consultar_contexto: consultarContexto, buscar_series: buscarSeries, consultar_dados: consultarDados,
  analisar_componentes: analisarComponentes, consultar_metodologia: consultarMetodologia,
};

// cache por snapshot + ferramenta + argumentos; o contexto da tela entra só na chave do consultar_contexto
const cache = new Map<string, Envelope>();

export function executarFerramenta(c: Contexto, nome: FerramentaDeDados, entrada: unknown): Envelope {
  const validada = schemas[nome].safeParse(entrada);
  if (!validada.success) return envelope(c.pacote, "erro_parametro", { erro: z.prettifyError(validada.error) });
  const chave = `${c.pacote.snapshot_id}|${nome}|${JSON.stringify(validada.data)}${nome === "consultar_contexto" ? JSON.stringify([c.estado, c.acompanhar]) : ""}`;
  if (!cache.has(chave)) {
    if (cache.size > 500) cache.delete(cache.keys().next().value!);
    cache.set(chave, executores[nome](c, validada.data));
  }
  return cache.get(chave)!;
}

// ==== 9. controlar_dashboard: o contrato da ação de interface ====
export function schemaControlarDashboard(pacote: Pacote) {
  // o alvo só pode ser uma visualização registrada, e o destaque só uma série que aparece nela
  const ids = pacote.visualizacoes.map((v) => v.id) as [string, ...string[]];
  const abas = [...new Set(pacote.visualizacoes.flatMap((v) => v.abas))] as [string, ...string[]];
  return z.discriminatedUnion("acao", [
    z.strictObject({
      acao: z.literal("mostrar"),
      visualizacao: z.enum(ids),
      aba: z.enum(abas).optional().describe("só quando a visualização aparece em mais de uma aba"),
      destacar_serie: ID_SERIE.optional().describe("id de uma série que aparece na visualização"),
    }).superRefine((e, ctx) => {
      const v = pacote.visualizacoes.find((x) => x.id === e.visualizacao)!;
      if (e.aba && !v.abas.includes(e.aba)) ctx.addIssue({ code: "custom", message: `${e.visualizacao} não está na aba ${e.aba}; está em ${v.abas.join(", ")}` });
      if (e.destacar_serie && (!v.destaques_suportados.length || !v.series.some((s) => s.serie_id === e.destacar_serie)))
        ctx.addIssue({ code: "custom", message: `não dá para destacar ${e.destacar_serie} em ${e.visualizacao}; séries: ${v.series.map((s) => s.serie_id).join(", ") || "nenhuma destacável"}` });
    }),
    z.strictObject({ acao: z.literal("desfazer") }),
    z.strictObject({ acao: z.literal("restaurar_inicial") }),
  ]);
}

// o que o navegador pode devolver; qualquer outra coisa vira erro. Número econômico não entra aqui
export const resultadoDaAcao = z.strictObject({
  status: z.enum(["applied", "unsupported", "stale_state", "cancelled", "error"]),
  action_id: z.string().max(80),
  estado_aplicado: z.strictObject({ aba: z.string().max(30), visualizacao_em_foco: z.string().max(80).nullable(), destaque: z.string().max(80).nullable(), revisao: z.number().int() }).nullable(),
  mensagem: z.string().max(200).optional(),
});
