// Estado da sessão. A seleção vive só nesta aba e some ao fechá-la (RF27, RF42, RN07).

import { K_PADRAO, STORAGE } from './config.js';

export const S = {
  view: 'inicio', etapa: null, picks: [], analisado: false, trilhaFeita: false,
  gapSev: 'todas', jobQ: '', jobNv: 'todos', jobArea: 'todos',
  graphCat: 'todas', graphPred: true, graphFocus: '', graphTabela: false, tgTabela: null,
  k: K_PADRAO, perfil: 'todos', modelo: 'auto', trilha: null, trilhaChave: null,
  coPerfil: 'todos',
  lastFocus: null
};

export function lerProgresso() {
  try { return JSON.parse(sessionStorage.getItem(STORAGE.progresso)) || {}; } catch { return {}; }
}

export function salvarProgresso(extra) {
  try {
    const atual = { picks: S.picks.slice(), analisado: S.analisado };
    sessionStorage.setItem(STORAGE.progresso, JSON.stringify(Object.assign(lerProgresso(), atual, extra || {})));
  } catch { /* sem armazenamento de sessão: segue só em memória */ }
}

/** Versões anteriores gravavam a seleção em localStorage, que sobrevive à sessão. */
export function descartarProgressoPersistente() {
  try {
    localStorage.removeItem(STORAGE.progresso);
    localStorage.removeItem('edutrack2-progresso');
  } catch { /* nada a apagar */ }
}
