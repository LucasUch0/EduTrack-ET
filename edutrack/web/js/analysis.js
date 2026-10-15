// Contas do perfil do estudante feitas no navegador, sobre os dados reais do serviço.
// Trilha, afinidade, diagnóstico do curso e normalização são calculados pelo serviço (servico.js);
// aqui ficam só as somas de conjunto que a tela refaz a cada disciplina marcada, com as mesmas
// definições do serviço: demanda = fração das vagas que pedem a competência.

import { habilidades, vagas, sugestoes, SUGESTOES_INFO } from './dados.js';
import { GRADE, DX } from './catalog.js';
import { S } from './state.js';
import { PRIORIDADE, ALCANCE_MINIMO } from './config.js';

const N_VAGAS = vagas.length || 1;

/** Competências cobertas pelas disciplinas marcadas (RF27). */
export function dominadas() {
  const set = new Set();
  GRADE.filter((d) => S.picks.includes(d.cod)).forEach((d) => d.skills.forEach((s) => set.add(s)));
  return set;
}

/** Fração das vagas que pedem a competência. */
export const parcela = (h) => h.vagas / N_VAGAS;

export const severidade = (p) => (p >= PRIORIDADE.alta ? 'danger' : (p >= PRIORIDADE.media ? 'warn' : 'info'));

/** Lacunas do estudante frente às vagas, da mais pedida para a menos (RF28). */
export function lacunasDoPerfil() {
  const dom = dominadas();
  return habilidades.filter((h) => h.vagas > 0 && !dom.has(h.n)).sort((a, b) => b.vagas - a.vagas || a.n.localeCompare(b.n, 'pt-BR')).map((h) => ({
    h,
    p: parcela(h),
    sev: severidade(parcela(h)),
    naGrade: h.disc > 0,
    dSug: sugestoes[h.n] ? DX[sugestoes[h.n]] : null,
    sugInfo: SUGESTOES_INFO[h.n] || null
  }));
}

/** A vaga em que o estudante já tem a maior parte dos requisitos (empate: a que pede mais coisas). */
export function vagaMaisCompativel(dom) {
  let melhor = null;
  vagas.forEach((v) => {
    if (!v.skills.length) return;
    const p = v.skills.filter((s) => dom.has(s)).length / v.skills.length;
    if (!melhor || p > melhor.p || (p === melhor.p && v.skills.length > melhor.v.skills.length)) melhor = { v, p };
  });
  return melhor;
}

export function vagasAoAlcance(dom) {
  return vagas.filter((v) => v.skills.length && v.skills.filter((s) => dom.has(s)).length >= Math.ceil(v.skills.length * ALCANCE_MINIMO)).length;
}

/** Parcela da demanda (competências pesadas pelo número de vagas) que o conjunto cobre (RF30). */
export function aderencia(set) {
  let tot = 0;
  let tem = 0;
  habilidades.forEach((h) => {
    tot += h.vagas;
    if (set.has(h.n)) tem += h.vagas;
  });
  return tot ? tem / tot : 0;
}
