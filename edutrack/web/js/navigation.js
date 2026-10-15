// Abas, etapas da trilha e menu. Não importa nenhuma tela: elas se registram.

import { S } from './state.js';
import { esc, toast } from './ui.js';

export const VIEWS = {
  inicio: { t: 'Início', d: 'Como funciona', lock: false },
  perfil: { t: 'Suas disciplinas', d: 'Marque as disciplinas concluídas', lock: false },
  diagnostico: { t: 'O que falta', d: 'O que você já sabe e o que falta', lock: true },
  trilha: { t: 'Sua trilha', d: 'Disciplinas para cursar, em ordem', lock: true },
  mercado: { t: 'Mercado', d: 'Vagas e competências mais pedidas', lock: false },
  coordenacao: { t: 'Coordenação', d: 'Lacunas curriculares do curso', lock: false },
  sobre: { t: 'Sobre', d: 'Ficha técnica e origem dos dados', lock: false }
};

/** As três etapas do estudante ficam sob uma entrada só do menu ("Minha trilha"). */
const JORNADA = ['perfil', 'diagnostico', 'trilha'];
const MENU = [
  { go: 'jornada', t: 'Minha trilha', d: 'Suas disciplinas, o que falta e a trilha' },
  { go: 'mercado', t: VIEWS.mercado.t, d: VIEWS.mercado.d },
  { go: 'coordenacao', t: VIEWS.coordenacao.t, d: VIEWS.coordenacao.d },
  { go: 'sobre', t: VIEWS.sobre.t, d: VIEWS.sobre.d }
];
const ganchos = {};

/** `antes` roda antes de exibir (dados atuais); `depois`, quando a aba já tem layout. */
export function registerViewHooks(id, { antes, depois } = {}) {
  ganchos[id] = { antes, depois };
}

export const locked = (id) => !!VIEWS[id] && VIEWS[id].lock && !S.analisado;

/** "Minha trilha" volta à etapa em que o estudante parou. */
function etapaAtual() {
  const e = S.etapa && !locked(S.etapa) ? S.etapa : null;
  return e || (S.analisado ? 'diagnostico' : 'perfil');
}

/** Tela indicada no endereço (#/trilha), para Voltar, Avançar e recarregar funcionarem. */
export const vistaDoEndereco = () => {
  const v = location.hash.replace(/^#\/?/, '');
  return VIEWS[v] ? v : null;
};

export function go(id, inicial, { historico = true } = {}) {
  if (id === 'jornada') id = etapaAtual();
  if (!VIEWS[id]) return;
  if (locked(id)) {
    // ao abrir um link antigo (#/trilha) numa sessão nova, só leva à etapa 1, sem aviso
    if (!inicial) toast('warn', 'Marque suas disciplinas primeiro', 'Escolha ao menos uma disciplina e clique em "Ver o que falta".');
    id = 'perfil';
  }
  const endereco = `#/${id}`;
  if (inicial) history.replaceState(null, '', endereco);
  else if (historico && location.hash !== endereco) history.pushState(null, '', endereco);
  S.view = id;
  if (JORNADA.includes(id)) S.etapa = id;
  ganchos[id]?.antes?.();
  document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
  document.getElementById(`v-${id}`).classList.add('active');
  const alvo = JORNADA.includes(id) ? 'jornada' : id;
  document.querySelectorAll('.navlink').forEach((b) => {
    if (b.dataset.go === alvo) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  document.title = `EduTrack · ${VIEWS[id].t}`;
  renderStepper();
  closeSheet();
  if (!inicial) {
    window.scrollTo({ top: 0 });
    document.getElementById('main').focus({ preventScroll: true });
  }
  ganchos[id]?.depois?.();
}

/** Indicador 1 · 2 · 3 acima das telas da trilha: mostra onde o estudante está e o que já fez (H1). */
function renderStepper() {
  const st = document.getElementById('stepper');
  const i = JORNADA.indexOf(S.view);
  st.hidden = i === -1;
  if (i === -1) return;
  st.querySelectorAll('.stp').forEach((b) => {
    const j = JORNADA.indexOf(b.dataset.go);
    b.disabled = locked(b.dataset.go);
    b.classList.toggle('done', j < i);
    if (j === i) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
  });
}

export function syncLocks() {
  renderStepper();
  renderSheet();
}

export function renderSheet() {
  document.getElementById('sheetGrid').innerHTML = MENU.map((m) => `<button class="sheet-item" data-go="${m.go}">`
    + `<div class="si-t">${esc(m.t)}</div><div class="si-d">${esc(m.d)}</div></button>`).join('');
}

export function closeSheet() {
  document.getElementById('sheet').classList.remove('open');
  document.getElementById('menuBtn').setAttribute('aria-expanded', 'false');
}

export function initNavigation() {
  const sheet = document.getElementById('sheet');
  const menuBtn = document.getElementById('menuBtn');

  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-go]');
    if (t && !t.disabled) go(t.dataset.go);
  });
  menuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const aberto = !sheet.classList.contains('open');
    sheet.classList.toggle('open', aberto);
    menuBtn.setAttribute('aria-expanded', String(aberto));
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#sheet') && !e.target.closest('#menuBtn')) closeSheet();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });
  // Voltar e Avançar do navegador trocam de tela em vez de sair do site
  window.addEventListener('popstate', () => {
    const v = vistaDoEndereco();
    if (v && v !== S.view) go(v, false, { historico: false });
  });
}
