// Índices derivados dos dados: o que está no PPC processado e quem ensina cada competência.

import { CATEGORIAS, habilidades, disciplinas, PREREQ } from './dados.js';
import { PPC } from './config.js';

export const PERIODOS = Array.from({ length: PPC.totalPeriodos }, (_, i) => i + 1);

disciplinas.forEach((d) => {
  d.stub = !PPC.periodosProcessados.includes(d.periodo);
  d.pre = PREREQ[d.cod] || [];
  d.nSkills = d.skills.length;
  d.oficial = d.fonte === 'programa_oficial';
});

/** Disciplinas que entram na análise e na recomendação. */
export const GRADE = disciplinas.filter((d) => !d.stub);

export const DX = {};
disciplinas.forEach((d) => { DX[d.cod] = d; });

habilidades.forEach((h) => {
  h.discs = GRADE.filter((d) => d.skills.includes(h.n)).map((d) => d.cod);
  h.disc = h.discs.length;
  h.catNome = CATEGORIAS[h.cat] || '';
});

export const HX = {};
habilidades.forEach((h) => { HX[h.n] = h; });

/** Identificação curta da disciplina: código oficial e carga horária, ou a origem da ementa. */
export function codTxt(d) {
  if (!d) return '';
  if (d.codigo) return `Cód. ${d.codigo}${d.ch ? ` · ${d.ch}h` : ''}`;
  return 'ementa de referência';
}

/** Nomes curtos dos pré-requisitos. */
export const nomesPre = (d) => d.pre.map((c) => (DX[c] ? DX[c].nome : c));

/** Cobertura declarada ao usuário (RF10, RF10a, RN06, RNF21). */
export const COBERTURA = {
  periodos: PPC.periodosProcessados.length,
  totalPeriodos: PPC.totalPeriodos,
  disciplinas: GRADE.length,
  esperadas: PPC.disciplinasEsperadas,
  oficiais: GRADE.filter((d) => d.oficial).length,
  referencia: GRADE.filter((d) => !d.oficial).length,
  foraDoPpc: PERIODOS.filter((p) => !PPC.periodosProcessados.includes(p)),
  divergente: GRADE.length !== PPC.disciplinasEsperadas,
  semCompetencia: GRADE.filter((d) => !d.skills.some((s) => HX[s]))
};
