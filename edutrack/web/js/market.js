// Mercado — competências mais exigidas e as vagas de TI de Manaus coletadas pelo pipeline.

import { habilidades, vagas } from './dados.js';
import { COLETA, PERFIS } from './config.js';
import { S } from './state.js';
import { dominadas } from './analysis.js';
import { esc, deb, vazio, dataCurta } from './ui.js';
import { openSkill } from './details.js';

const el = (id) => document.getElementById(id);
const SETA_FORA = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true" style="width:13px;height:13px"><path d="M14 4h6v6"/><line x1="20" y1="4" x2="11" y2="13"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>';

const VISTO = '<svg class="i chk-i" viewBox="0 0 24 24" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
const POR_PAGINA = 10;
const MAX_SELOS = 6;
let limite = POR_PAGINA;

export function renderMercado() {
  const dom = dominadas();
  const top = habilidades.filter((h) => h.vagas > 0).sort((a, b) => b.vagas - a.vagas || a.n.localeCompare(b.n, 'pt-BR')).slice(0, 12);
  const mx = top.length ? top[0].vagas : 1;
  el('topSkills').innerHTML = '<ol class="top-list">' + top.map((h) => {
    const tem = S.analisado && dom.has(h.n);
    return `<li class="top-row${tem ? ' tem' : ''}"><button type="button" class="nm" data-sk="${esc(h.n)}" title="Onde aprender ${esc(h.n)}">${tem ? VISTO : ''}${esc(h.n)}${tem ? '<span class="sr"> (você tem)</span>' : ''}</button>`
      + `<span class="vv">${h.vagas}</span>`
      + `<span class="track" aria-hidden="true"><span class="fill" style="width:${Math.round(h.vagas / mx * 100)}%"></span></span></li>`;
  }).join('') + '</ol>'
    + `<p class="nota-fina">${S.analisado ? '✓ = você já tem, pelas disciplinas marcadas. ' : ''}Clique numa competência para ver em que disciplinas aprendê-la.</p>`;
  limite = POR_PAGINA;
  renderJobs();
}

/** Parcela dos requisitos da vaga que o estudante já cobre. */
const aderenciaVaga = (v, dom) => (v.skills.length ? v.skills.filter((s) => dom.has(s)).length / v.skills.length : 0);

function selo(nome, tem) {
  return `<span class="chip-s${tem ? '' : ' neutro'}">${tem ? VISTO : ''}${esc(nome)}${tem ? '<span class="sr"> (você tem)</span>' : ''}</span>`;
}

function renderJobs() {
  const dom = dominadas();
  const q = S.jobQ.trim().toLowerCase();
  let lista = vagas.filter((v) => {
    const nivelOk = S.jobNv === 'todos' || v.niveis.includes(S.jobNv);
    const areaOk = S.jobArea === 'todos' || v.perfil === S.jobArea;
    const texto = `${v.cargo} ${v.empresa} ${v.skills.join(' ')}`.toLowerCase();
    return nivelOk && areaOk && (!q || texto.includes(q));
  });
  if (S.analisado) lista = lista.slice().sort((a, b) => aderenciaVaga(b, dom) - aderenciaVaga(a, dom));
  el('jobsCount').textContent = `${lista.length} de ${vagas.length} vagas${S.analisado ? ' · as mais próximas do seu perfil primeiro' : ''}`;
  const host = el('jobs');
  if (!lista.length) {
    host.innerHTML = vazio('info', 'Nenhuma vaga encontrada', 'Tente outro cargo, empresa, área ou nível.');
    return;
  }
  const visiveis = lista.slice(0, limite);
  host.innerHTML = visiveis.map((v) => {
    const pc = Math.round(aderenciaVaga(v, dom) * 100);
    const nivel = v.niveis.length ? v.niveis.join('/') : '';
    const meta = [v.empresa, nivel, v.modalidade].filter(Boolean);
    // as competências que o estudante tem vêm primeiro; o resto fica resumido em "+N"
    const skills = v.skills.slice().sort((a, b) => Number(dom.has(b)) - Number(dom.has(a)));
    const extra = skills.length - MAX_SELOS;
    return '<article class="job">'
      + '<div class="job-h">'
        + `<div><h3>${esc(v.cargo)}</h3><p class="co">${meta.map(esc).join(' · ')}</p></div>`
        + (S.analisado ? `<span class="match ${pc >= 60 ? 'hi' : (pc >= 30 ? 'md' : 'lo')}" title="Você já tem ${pc}% do que esta vaga pede">${pc}% compatível</span>` : '')
      + '</div>'
      + `<div class="chips">${skills.slice(0, MAX_SELOS).map((s) => selo(s, dom.has(s))).join('')}`
        + skills.slice(MAX_SELOS).map((s) => selo(s, dom.has(s)).replace('class="chip-s', 'hidden class="chip-s extra')).join('')
        + (extra > 0 ? `<button type="button" class="chip-s neutro chip-mais" aria-label="+${extra} competências: mostrar todas">+${extra}</button>` : '') + '</div>'
      + (v.url ? `<a class="job-link" href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">Ver anúncio${SETA_FORA}<span class="sr"> de ${esc(v.cargo)} (abre o site ${esc(COLETA.dominio)} em nova aba)</span></a>` : '')
      + '</article>';
  }).join('')
  + (lista.length > visiveis.length
    ? `<div class="mais"><button type="button" class="btn btn-line btn-sm" id="jobsMais">Mostrar mais (${lista.length - visiveis.length} restantes)</button></div>`
    : '');
  el('jobsMais')?.addEventListener('click', () => {
    const antes = limite;
    limite += POR_PAGINA;
    renderJobs();
    const alvo = host.querySelectorAll('.job h3')[antes];
    if (alvo) { alvo.tabIndex = -1; alvo.focus(); }
  });
}

export function initMarket() {
  el('coletaInfo').textContent = `${COLETA.aceitas} vagas de tecnologia coletadas no ${COLETA.fonte} em ${dataCurta(COLETA.data)}. O nível vem só do título do anúncio.`;
  const area = el('jobArea');
  Object.entries(PERFIS).filter(([k]) => k !== 'todos').forEach(([k, p]) => {
    const o = document.createElement('option');
    o.value = k;
    o.textContent = `${p.t} (${p.vagas})`;
    area.appendChild(o);
  });
  // "+N" mostra as competências restantes da vaga (funciona no toque, ao contrário de uma dica ao passar o mouse)
  el('jobs').addEventListener('click', (e) => {
    const b = e.target.closest('.chip-mais');
    if (!b) return;
    const extras = [...b.parentElement.querySelectorAll('.extra')];
    extras.forEach((x) => { x.hidden = false; });
    b.remove();
    if (extras[0]) { extras[0].tabIndex = -1; extras[0].focus(); }  // o foco não se perde com o botão removido
  });
  el('topSkills').addEventListener('click', (e) => { const b = e.target.closest('[data-sk]'); if (b) openSkill(b.dataset.sk); });
  const filtrar = () => { limite = POR_PAGINA; renderJobs(); };
  area.addEventListener('change', function () { S.jobArea = this.value; filtrar(); });
  el('jobNivel').addEventListener('change', function () { S.jobNv = this.value; filtrar(); });
  el('jobSearch').addEventListener('input', deb(function () { S.jobQ = this.value; filtrar(); }, 220));
}
