// Conferência da resposta antes de o painel marcá-la como concluída.
// Cada número com unidade (% ou pp) no texto precisa bater com uma evidência que as ferramentas devolveram neste
// turno, arredondada nas casas que o texto usa; cada id citado precisa existir; e o texto não pode dizer que abriu
// ou destacou algo na tela sem uma ação confirmada ("applied"). Isso reduz o risco de número inventado, mas não o
// elimina: um número certo pode estar na frase errada, e essa leitura continua sendo do economista.

import type { Evidencia } from "./pacote.js";

export type Verificacao = {
  status: "verificada" | "com_alertas";
  numeros_conferidos: number;
  numeros_sem_evidencia: string[];
  citacoes_inexistentes: string[];
  citacoes_divergentes: string[];
  acao_de_tela_sem_confirmacao: boolean;
};

const CITACAO = /\[(E-[0-9a-f]{6})\]/g;
// número com vírgula ou ponto decimal, com sinal opcional, seguido de % ou pp
const NUMERO = /([+−-]?)(\d+(?:[.,]\d+)?)\s?(%|pp|p\.p\.)/g;
// o grupo de citações que vem depois do número, até o fim da frase: "3,79% (−0,05 pp) [E-a] [E-b]"
const GRUPO_DE_CITACOES = /^([^.\n]*?)((?:\s*\[E-[0-9a-f]{6}\])+)/;
const TEM_NUMERO = /\d+(?:[.,]\d+)?\s?(%|pp|p\.p\.)/;
const AFIRMA_ACAO = /\b(abri|abrimos|estou mostrando|destaquei|deixei aberto|mostrei no gr[aá]fico|coloquei na tela|est[aá] aberto na tela)\b/i;

function casa(valorDoTexto: number, casas: number, evidencia?: Evidencia) {
  // o texto pode escrever sem sinal ("recuou 0,14 pp"), então comparo em módulo, na precisão que o texto mostra
  if (evidencia?.valor == null) return false;
  return Math.abs(Math.abs(evidencia.valor) - Math.abs(valorDoTexto)) <= 0.5 * 10 ** -casas + 1e-9;
}

export function verificarResposta(texto: string, evidencias: Map<string, Evidencia>, houveAcaoAplicada: boolean): Verificacao {
  const citadas = [...texto.matchAll(CITACAO)].map((m) => m[1]);
  const inexistentes = [...new Set(citadas.filter((id) => !evidencias.has(id)))];
  const semEvidencia: string[] = [], divergentes: string[] = [];
  let conferidos = 0;
  for (const m of texto.matchAll(NUMERO)) {
    const antes = texto.slice(Math.max(0, m.index! - 25), m.index!).toLowerCase();
    // a meta do Banxico é um parâmetro do painel, não um dado do release
    if (/meta/.test(antes) && m[2] === "3") continue;
    const valor = Number(m[2].replace(",", "."));
    const casas = (m[2].split(/[.,]/)[1] ?? "").length;
    // o grupo de citações logo depois do número é dele se nenhum outro número vier antes; numa conta como
    // "0,33% − 0,11 pp = 0,22% [E-x]" a citação é só do resultado. Do grupo, basta uma bater
    const depois = texto.slice(m.index! + m[0].length, m.index! + m[0].length + 80);
    const grupo = GRUPO_DE_CITACOES.exec(depois);
    const citacoes = grupo && !TEM_NUMERO.test(grupo[1]) ? [...grupo[2].matchAll(CITACAO)].map((c) => c[1]).filter((id) => evidencias.has(id)) : [];
    conferidos++;
    if (citacoes.length) {
      if (!citacoes.some((id) => casa(valor, casas, evidencias.get(id)))) divergentes.push(`${m[0]} ≠ ${citacoes.join(", ")}`);
    } else if (![...evidencias.values()].some((ev) => casa(valor, casas, ev))) {
      semEvidencia.push(m[0].trim());
    }
  }
  const acaoSemConfirmacao = !houveAcaoAplicada && AFIRMA_ACAO.test(texto);
  const limpa = !inexistentes.length && !semEvidencia.length && !divergentes.length && !acaoSemConfirmacao;
  return { status: limpa ? "verificada" : "com_alertas", numeros_conferidos: conferidos, numeros_sem_evidencia: semEvidencia,
           citacoes_inexistentes: inexistentes, citacoes_divergentes: divergentes, acao_de_tela_sem_confirmacao: acaoSemConfirmacao };
}
