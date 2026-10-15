// Etapa 2 — o que o estudante já tem e o que falta frente às vagas (RF28).

import { vagas } from './dados.js';
import { HX, DX } from './catalog.js';
import { PRIORIDADE } from './config.js';
import { S } from './state.js';
import { dominadas, lacunasDoPerfil, vagaMaisCompativel, aderencia } from './analysis.js';
import { openSkill } from './details.js';
import { tornarAcionavel } from './accessibility.js';
import { esc, kpi, vazio, grupoDePills, pct } from './ui.js';

const el = (id) => document.getElementById(id);

export function renderDiagnostico() {
  const dom = dominadas();
  const n = S.picks.length;
  const cob = aderencia(dom);
  const pedidas = [...dom].filter((x) => HX[x] && HX[x].vagas > 0).length;
  const mv = vagaMaisCompativel(dom);

  el('diagSub').textContent = `Suas ${n} ${n === 1 ? 'disciplina' : 'disciplinas'} comparadas com o que ${vagas.length} vagas de tecnologia de Manaus pedem.`;
  el('kpis').innerHTML = [
    { v: pct(cob), l: 'Sua cobertura do mercado', s: 'do que as vagas pedem, você já sabe isso' },
    { v: dom.size, l: dom.size === 1 ? 'Competência que você tem' : 'Competências que você tem', s: `${pedidas} ${pedidas === 1 ? 'delas é pedida' : 'delas são pedidas'} por empresas` },
    mv
      ? { v: pct(mv.p), l: 'Vaga mais compatível', s: `do que "${esc(mv.v.cargo)}" pede, você já tem` }
      : { v: '—', l: 'Vaga mais compatível', s: 'nenhuma vaga com requisitos reconhecidos' }
  ].map(kpi).join('');

  el('comoLer').innerHTML = '<ul class="glossario">'
    + '<li><b>Competência</b> é um conhecimento ou habilidade que as vagas pedem, como SQL, Redes ou Inglês.</li>'
    + `<li><b>Cobertura do mercado</b> é quanto das competências pedidas pelas ${vagas.length} vagas você já tem. As mais pedidas valem mais: saber algo pedido em 40 de cada 100 vagas conta mais que saber algo pedido em uma vaga só.</li>`
    + '<li><b>Vaga mais compatível</b> é a vaga em que você já tem a maior parte dos requisitos.</li>'
    + `<li><b>Prioridade</b>: <b>alta</b> = pedida em ${Math.round(100 * PRIORIDADE.alta)} ou mais de cada 100 vagas; <b>média</b> = entre ${Math.round(100 * PRIORIDADE.media)} e ${Math.round(100 * PRIORIDADE.alta)}; <b>baixa</b> = menos de ${Math.round(100 * PRIORIDADE.media)}.</li>`
    + '</ul>';

  const domList = [...dom].map((x) => HX[x]).filter(Boolean).sort((a, b) => b.vagas - a.vagas || a.n.localeCompare(b.n, 'pt-BR'));
  el('domina').innerHTML = domList.length
    ? `<div class="chips">${domList.map((h) => `<span class="chip-s">${esc(h.n)}<span class="chip-n">${h.vagas} ${h.vagas === 1 ? 'vaga' : 'vagas'}</span></span>`).join('')}</div>`
    : vazio('info', 'Nenhuma disciplina marcada', 'Volte à etapa 1 e marque o que já concluiu.');

  renderGaps();
}

const SEV = { danger: 'hi', warn: 'md', info: 'lo' };
const ROTULO = { danger: 'Alta', warn: 'Média', info: 'Baixa' };
const SELO = { danger: 'tag-rose', warn: 'tag-amber', info: 'tag-sky' };

const POR_PAGINA = 8;
let limite = POR_PAGINA;

/** Uma ação concreta por lacuna, em uma linha. */
function comoAprender(g) {
  const h = g.h;
  if (g.naGrade) return `Curse ${esc(h.discs.map((c) => (DX[c] ? DX[c].nome : c)).join(' ou '))}`;
  if (g.dSug) return `Nenhuma disciplina ensina · a IA sugere começar por ${esc(g.dSug.nome)}`;
  return 'Nenhuma disciplina ensina · aprenda por fora (cursos, projetos, estágio)';
}

function renderGaps() {
  const todas = lacunasDoPerfil();
  const filtradas = todas.filter((g) => S.gapSev === 'todas' || g.sev === S.gapSev);
  const lista = filtradas.slice(0, limite);
  const host = el('gapHost');
  const dom = dominadas();
  if (!lista.length) {
    host.innerHTML = vazio('ok', 'Nada nesta prioridade', 'Escolha outro filtro para ver as demais competências.');
    return;
  }
  host.innerHTML = '<div class="gap-cols" aria-hidden="true"><span>Competência e como aprender</span><span>Pedida em</span><span>Se aprender, sua cobertura vai a</span><span>Prioridade</span></div>'
    + lista.map((g) => {
      const h = g.h;
      const com = new Set(dom);
      com.add(h.n);
      const depois = aderencia(com);
      return `<div class="gap-card ${SEV[g.sev]}" role="button" data-sk="${esc(h.n)}" aria-label="${esc(`${h.n}: pedida em ${pct(g.p)} das vagas; se aprender, sua cobertura vai a ${pct(depois)}; prioridade ${ROTULO[g.sev].toLowerCase()}. Abrir detalhes.`)}">`
        + `<div class="gr-main"><h3>${esc(h.n)}</h3><p>${comoAprender(g)}</p></div>`
        + `<div class="gr-num"><b>${pct(g.p)}</b><span class="u"> das vagas</span></div>`
        + `<div class="gr-num gain"><b>${pct(depois)}</b></div>`
        + `<span class="tag ${SELO[g.sev]}"><span class="sr">Prioridade </span>${ROTULO[g.sev]}</span>`
        + '</div>';
    }).join('')
    + (filtradas.length > lista.length
      ? `<div class="mais"><button type="button" class="btn btn-line btn-sm" id="gapMais">Mostrar mais (${filtradas.length - lista.length} restantes)</button></div>`
      : '');
  host.querySelectorAll('.gap-card[data-sk]').forEach((r) => tornarAcionavel(r, () => openSkill(r.dataset.sk)));
  el('gapMais')?.addEventListener('click', () => {
    const antes = limite;
    limite += POR_PAGINA;
    renderGaps();
    host.querySelectorAll('.gap-card')[antes]?.focus();
  });
}

export function initDiagnostic() {
  grupoDePills(el('gapPills'), (p) => { S.gapSev = p.dataset.sev; limite = POR_PAGINA; renderGaps(); });
}
