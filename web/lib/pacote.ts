// O pacote de dados do assistente e as consultas sobre ele.
// O pacote é gerado pelo pipeline em Python (pipeline/3_dashboard/pacote_assistente.py) a partir dos mesmos
// resultados que alimentam o dashboard. Aqui eu só filtro, ordeno e seleciono. As únicas contas são a soma e a
// subtração de incidências já exportadas (decomposição e resíduo) e a diferença entre duas taxas exportadas
// (mudança da taxa em pp, a mesma conta que o cartão do dashboard faz). Nenhuma fórmula econômica é refeita aqui.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// ==== 1. Tipos e carga ====
export type Frequencia = "mensal" | "quinzenal";
export type Serie = {
  id: string; tipo: "componente" | "generico" | "generico_saido" | "indicador"; nome_oficial: string; nome_exibicao: string;
  aliases: string[]; nivel: number | null; pai: string | null; filhos: string[]; cobertura: Partial<Record<Frequencia, [string, string]>>;
  cestas: string[]; codigo_generico?: string; peso_cesta_2024?: number; peso_cesta_2018?: number;
};
export type Metrica = { nome: string; unidade: string; natureza: string; fonte: string; tema_metodologia: string; limitacao?: string;
  validacao: { status: string; escopo: string; desvio_maximo_pp?: number };
  para_genericos?: { natureza: string; fonte: string; validacao: { status: string; escopo: string } } };
export type Visualizacao = { id: string; tipo: "grafico" | "tabela"; titulo: string; subtitulo: string; abas: string[]; aba_principal: string;
  series: { serie_id: string; rotulo: string }[]; metricas: string[]; frequencia: string; unidade: string; janela: [string, string] | null;
  destaques_suportados: string[]; filtros_suportados: string[] };
export type Trecho = { id: string; arquivo: string; secao: string; texto: string };
export type Pacote = {
  snapshot_id: string; gerado_em: string; versao_pacote: number;
  release: { tipo: string; frequencia_do_release: Frequencia; periodo: string; rotulo: string; descricao: string;
             ultimo_periodo: Record<Frequencia, string>; ultimo_rotulo: Record<Frequencia, string> };
  validacao: { data: string; checagens: Record<string, { desvio_maximo_pp: number; ok: boolean }> };
  metricas: Record<string, Metrica>; series: Serie[];
  valores: Record<string, Partial<Record<Frequencia, { periodos: string[]; rotulos: string[]; [metrica: string]: (number | null)[] | string[] }>>>;
  expectativas: { periodo: string; rotulo_periodo: string; indicador: string; esperado: number; realizado: number | null; fonte: string; unidade: string }[];
  estimativa_do_mes: any; destaques: any;
  parametros: { anos_padrao_sazonal: [number, number]; minimo_anos_padrao_sazonal: number; meta_banxico: number; meses_de_genericos: number };
  visualizacoes: Visualizacao[];
  metodologia: { versao: string; temas: Record<string, string[]>; trechos: Trecho[] };
};

let emCache: Pacote | null = null;

export function carregarPacote(caminho = join(process.cwd(), "dados", "pacote.json")): Pacote {
  // leio uma vez por instância da função; o pacote é o retrato do release e não muda enquanto ela vive
  if (!emCache) emCache = JSON.parse(readFileSync(caminho, "utf-8")) as Pacote;
  return emCache;
}

// ==== 2. Envelope comum e evidências ====
export type Evidencia = {
  id: string; tipo: "numero" | "derivado" | "estimado" | "metodologia" | "expectativa"; rotulo: string; serie_id?: string; metrica?: string; valor?: number | null;
  unidade?: string; periodo?: string; rotulo_periodo?: string; frequencia?: string; natureza?: string; origem: string;
  validacao?: { status: string; escopo: string }; visualizacao?: string | null; texto?: string;
};
export type Envelope = { status: string; snapshot_id: string; dados: unknown; evidencias: Evidencia[]; limitacoes: string[] };

export function envelope(pacote: Pacote, status: string, dados: unknown, evidencias: Evidencia[] = [], limitacoes: string[] = []): Envelope {
  return { status, snapshot_id: pacote.snapshot_id, dados, evidencias, limitacoes };
}

function idDaEvidencia(pacote: Pacote, chave: string) {
  // o id depende só do snapshot e do que a evidência é: a mesma consulta dá o mesmo id em qualquer pedido
  return "E-" + createHash("sha1").update(`${pacote.snapshot_id}|${chave}`).digest("hex").slice(0, 6);
}

const serieDoId = (pacote: Pacote) => new Map(pacote.series.map((s) => [s.id, s]));
let indiceDeSeries: Map<string, Serie> | null = null;
export function serie(pacote: Pacote, id: string): Serie | undefined {
  if (!indiceDeSeries) indiceDeSeries = serieDoId(pacote);
  return indiceDeSeries.get(id);
}
export function trocarPacoteEmTeste(pacote: Pacote | null) {
  // só os testes usam: troca o pacote carregado e zera os índices
  emCache = pacote;
  indiceDeSeries = null;
}

export function metricaDaSerie(pacote: Pacote, s: Serie, metrica: string): Metrica {
  // a mesma métrica pode ter origem e validação diferentes num genérico (incidência calculada pelo projeto)
  const m = pacote.metricas[metrica];
  return s.tipo === "generico" && m.para_genericos ? { ...m, ...m.para_genericos } : m;
}

export function evidenciaNumero(pacote: Pacote, s: Serie, metrica: string, frequencia: Frequencia, periodo: string, rotulo: string, valor: number | null): Evidencia {
  const m = metricaDaSerie(pacote, s, metrica);
  return {
    id: idDaEvidencia(pacote, `${s.id}|${metrica}|${frequencia}|${periodo}`), tipo: "numero",
    rotulo: `${s.nome_exibicao}: ${m.nome}, ${rotulo}`, serie_id: s.id, metrica, valor, unidade: m.unidade, periodo, rotulo_periodo: rotulo,
    frequencia, natureza: m.natureza, origem: m.fonte, validacao: { status: m.validacao.status, escopo: m.validacao.escopo },
    visualizacao: visualizacaoPara(pacote, s.id, metrica, frequencia, periodo),
  };
}

export function evidenciaTrecho(pacote: Pacote, t: Trecho): Evidencia {
  return { id: idDaEvidencia(pacote, `trecho|${t.id}`), tipo: "metodologia", rotulo: `${t.arquivo} · ${t.secao}`, origem: `docs/${t.arquivo} (versão ${pacote.metodologia.versao})`, texto: t.texto };
}

export function evidenciaExpectativa(pacote: Pacote, e: Pacote["expectativas"][number]): Evidencia {
  return { id: idDaEvidencia(pacote, `expectativa|${e.periodo}|${e.indicador}`), tipo: "expectativa",
           rotulo: `Expectativa para ${e.indicador === "indice_general" ? "o INPC" : "o núcleo"}, ${e.rotulo_periodo}`, serie_id: e.indicador,
           valor: e.esperado, unidade: "%", periodo: e.periodo, rotulo_periodo: e.rotulo_periodo, natureza: "expectativa registrada", origem: e.fonte,
           validacao: { status: "fonte_externa_sem_conferencia", escopo: "número de fonte externa; o pipeline só registra a fonte e a data" },
           visualizacao: null };
}

export function evidenciaDerivada(pacote: Pacote, chave: string, tipo: "derivado" | "estimado", rotulo: string, valor: number, unidade: string, origem: string,
                                  visualizacao: string | null = null): Evidencia {
  // conta simples sobre valores já exportados (diferença de taxas, resíduo) ou a estimativa do pipeline; o rótulo diz qual
  return { id: idDaEvidencia(pacote, `${tipo}|${chave}`), tipo, rotulo, valor: Math.round(valor * 1e6) / 1e6, unidade, natureza: tipo, origem, visualizacao };
}

// as visualizações que só mostram o release valem só para o período do release
const SO_DO_RELEASE = new Set(["main_vs_norma", "decomp_arvore", "main_top_incidencias", "decomp_desvios", "main_ultimos_periodos"]);

export function visualizacaoPara(pacote: Pacote, serieId: string, metrica: string, frequencia: Frequencia, periodo: string): string | null {
  // prefiro tabela e gráfico do Resumo/Composição ao Explorar, porque é onde o leitor já está
  const candidatas = pacote.visualizacoes.filter((v) => v.series.some((s) => s.serie_id === serieId) && v.metricas.includes(metrica)
    && (!SO_DO_RELEASE.has(v.id) || (periodo === pacote.release.periodo && frequencia === pacote.release.frequencia_do_release))
    && (SO_DO_RELEASE.has(v.id) || frequencia === "mensal" || v.frequencia === "mensal_com_ultima_quinzena"));
  candidatas.sort((a, b) => Number(a.aba_principal === "explorar") - Number(b.aba_principal === "explorar"));
  return candidatas[0]?.id ?? null;
}

// ==== 3. Leitura de valores ====
export type Ponto = { periodo: string; rotulo: string; valor: number | null };

export function colunaDaSerie(pacote: Pacote, id: string, frequencia: Frequencia, metrica: string): Ponto[] | null {
  const tabela = pacote.valores[id]?.[frequencia];
  const coluna = tabela?.[metrica] as (number | null)[] | undefined;
  if (!tabela || !coluna) return null;
  return tabela.periodos.map((periodo, i) => ({ periodo, rotulo: tabela.rotulos[i], valor: coluna[i] }));
}

export function valorEm(pacote: Pacote, id: string, frequencia: Frequencia, metrica: string, periodo: string): Ponto | null {
  return colunaDaSerie(pacote, id, frequencia, metrica)?.find((p) => p.periodo === periodo) ?? null;
}

export function metricasDisponiveis(pacote: Pacote, id: string): Partial<Record<Frequencia, string[]>> {
  const valores = pacote.valores[id] ?? {};
  return Object.fromEntries(Object.entries(valores).map(([f, t]) => [f, Object.keys(t!).filter((k) => k !== "periodos" && k !== "rotulos")]));
}

export function hierarquia(pacote: Pacote, id: string): string[] {
  // do INPC até a série: "INPC geral > Núcleo > Mercadorias > ..."
  const caminho: string[] = [];
  let atual = serie(pacote, id);
  while (atual) {
    caminho.unshift(atual.nome_exibicao);
    atual = atual.pai ? serie(pacote, atual.pai) : undefined;
  }
  return caminho;
}

// ==== 4. Busca ====
export const normalizar = (texto: string) => texto.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

export type Candidato = { serie: Serie; correspondencia: "exata" | "aproximada"; pontuacao: number; nome_que_casou: string };

export function buscar(pacote: Pacote, termo: string): Candidato[] {
  // exata: o termo é o nome oficial, o nome na tela, um alias ou o id. Aproximada: o termo aparece como palavra
  // inteira num nome, ou o nome começa com ele. Sem palpite por semelhança de letras: "tomate" não vira "Tomate verde"
  // por acaso, vira ambiguidade explícita, porque os dois têm "tomate" como alias
  const q = normalizar(termo);
  if (!q) return [];
  const candidatos: Candidato[] = [];
  for (const s of pacote.series) {
    const nomes = [s.nome_oficial, s.nome_exibicao, ...s.aliases, s.id];
    const exato = nomes.find((n) => normalizar(n) === q);
    if (exato) { candidatos.push({ serie: s, correspondencia: "exata", pontuacao: 1, nome_que_casou: exato }); continue; }
    let melhor = 0, casou = "";
    for (const n of nomes) {
      const nn = normalizar(n);
      const pontos = ` ${nn} `.includes(` ${q} `) ? 0.8 : nn.startsWith(q) && q.length >= 3 ? 0.6 : 0;
      if (pontos > melhor) { melhor = pontos; casou = n; }
    }
    if (melhor) candidatos.push({ serie: s, correspondencia: "aproximada", pontuacao: melhor, nome_que_casou: casou });
  }
  // exatas primeiro; entre iguais, o componente antes do genérico e o de maior peso antes
  const peso = (s: Serie) => (s.tipo === "componente" ? 100 : s.peso_cesta_2024 ?? 0);
  return candidatos.sort((a, b) => b.pontuacao - a.pontuacao || peso(b.serie) - peso(a.serie));
}
