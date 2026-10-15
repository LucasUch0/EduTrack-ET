// Grafo da trilha do estudante: as disciplinas recomendadas e as competências que cada uma traz.
// É o recorte pessoal do grafo heterogêneo (disciplina → ensina → competência ← pedida pelas vagas),
// com a mesma informação em tabela para leitores de tela (WCAG 1.1.1).

import { S } from './state.js';
import { esc, pct } from './ui.js';

const el = (id) => document.getElementById(id);

const LINHA = 34;
const TOPO = 44;
const X_DISC = 330;
const X_COMP = 520;
const LARGURA = 860;
const MAX_ROTULO = 36;

const curto = (t) => (t.length > MAX_ROTULO ? `${t.slice(0, MAX_ROTULO - 1)}…` : t);

/** Competências na ordem em que a trilha as entrega; cada uma ligada às disciplinas que a trazem. */
function montar(T) {
  const comps = new Map();
  T.passos.forEach((p, i) => p.novas.forEach((h) => {
    if (!comps.has(h.nome)) comps.set(h.nome, { nome: h.nome, demanda: h.demanda, de: [] });
    comps.get(h.nome).de.push(i);
  }));
  return [...comps.values()];
}

function desenhar(T, comps) {
  const nD = T.passos.length;
  const nC = comps.length;
  const n = Math.max(nD, nC, 1);
  const altura = TOPO + n * LINHA + 12;
  const yD = (i) => TOPO + ((n - nD) * LINHA) / 2 + i * LINHA + LINHA / 2;
  const yC = (j) => TOPO + ((n - nC) * LINHA) / 2 + j * LINHA + LINHA / 2;
  const meio = (X_DISC + X_COMP) / 2;

  const arestas = [];
  comps.forEach((c, j) => c.de.forEach((i) => {
    arestas.push(`<path class="tg-e" data-d="${i}" data-c="${j}" d="M${X_DISC} ${yD(i)} C${meio} ${yD(i)}, ${meio} ${yC(j)}, ${X_COMP} ${yC(j)}"/>`);
  }));

  const discs = T.passos.map((p, i) => {
    const traz = p.novas.map((h) => h.nome).join(', ') || p.motivo;
    return `<g class="tg-n tg-d" data-d="${i}" tabindex="0" role="img" aria-label="${esc(`Passo ${i + 1}: ${p.d.nome}. Traz ${traz}.`)}">`
      + `<title>${esc(p.d.nome)}</title>`
      + `<circle cx="${X_DISC}" cy="${yD(i)}" r="7"/>`
      + `<text x="${X_DISC - 16}" y="${yD(i) + 4}" text-anchor="end"><tspan class="tg-num">${i + 1}.</tspan> ${esc(curto(p.d.nome))}</text></g>`;
  }).join('');

  const r = 7;
  const compsSvg = comps.map((c, j) => {
    const y = yC(j);
    return `<g class="tg-n tg-c" data-c="${j}" tabindex="0" role="img" aria-label="${esc(`${c.nome}: pedida em ${pct(c.demanda)} das vagas.`)}">`
      + `<title>${esc(c.nome)}</title>`
      + `<polygon points="${X_COMP},${y - r} ${X_COMP + r},${y} ${X_COMP},${y + r} ${X_COMP - r},${y}"/>`
      + `<text x="${X_COMP + 16}" y="${y + 4}">${esc(curto(c.nome))} <tspan class="tg-pct">${pct(c.demanda)}</tspan></text></g>`;
  }).join('');

  return `<svg class="tg-svg" viewBox="0 0 ${LARGURA} ${altura}" role="group" aria-label="Grafo da sua trilha: ${nD} disciplinas ligadas a ${nC} competências">`
    + `<text class="col-t" x="${X_DISC - 16}" y="20" text-anchor="end">DISCIPLINAS DA TRILHA</text>`
    + `<text class="col-t" x="${X_COMP + 16}" y="20">O QUE VOCÊ APRENDE · % DAS VAGAS</text>`
    + `<g>${arestas.join('')}</g>${discs}${compsSvg}</svg>`;
}

function tabela(T) {
  let acumulada = T.antes;
  return '<table class="tbl"><caption class="sr">Mesma informação do grafo: o que cada disciplina da trilha ensina</caption>'
    + '<thead><tr><th scope="col">Passo</th><th scope="col">Disciplina</th><th scope="col">O que você aprende (% das vagas que pedem)</th><th scope="col">Sua cobertura depois</th></tr></thead><tbody>'
    + T.passos.map((p, i) => {
      acumulada += p.ganho;
      // data-rotulo: no celular cada linha vira um cartão com o nome da coluna antes do valor
      return `<tr><td class="mono" data-rotulo="Passo">${i + 1}</td><td style="font-weight:600" data-rotulo="Disciplina">${esc(p.d.nome)}</td>`
        + `<td style="color:var(--ink-2)" data-rotulo="O que você aprende">${p.novas.length ? p.novas.map((h) => `${esc(h.nome)} (${pct(h.demanda)})`).join(', ') : `É ${esc(p.motivo)}`}</td>`
        + `<td class="mono" data-rotulo="Sua cobertura depois">${pct(acumulada)}</td></tr>`;
    }).join('')
    + '</tbody></table>';
}

/** Ao apontar ou focar um ponto, acende só as ligações dele. */
function ligarDestaque(svg) {
  const acender = (g) => {
    const chave = g.dataset.d != null ? `[data-d="${g.dataset.d}"]` : `[data-c="${g.dataset.c}"]`;
    svg.classList.add('foco');
    svg.querySelectorAll(`.tg-e${chave}`).forEach((e) => e.classList.add('hot'));
    const ligados = new Set();
    svg.querySelectorAll(`.tg-e${chave}`).forEach((e) => { ligados.add(`d${e.dataset.d}`); ligados.add(`c${e.dataset.c}`); });
    svg.querySelectorAll('.tg-n').forEach((n) => {
      const id = n.dataset.d != null ? `d${n.dataset.d}` : `c${n.dataset.c}`;
      n.classList.toggle('hot', ligados.has(id) || n === g);
    });
  };
  const apagar = () => {
    svg.classList.remove('foco');
    svg.querySelectorAll('.hot').forEach((x) => x.classList.remove('hot'));
  };
  svg.querySelectorAll('.tg-n').forEach((g) => {
    g.addEventListener('mouseenter', () => acender(g));
    g.addEventListener('focus', () => acender(g));
    g.addEventListener('mouseleave', apagar);
    g.addEventListener('blur', apagar);
  });
}

/** Em telas estreitas o grafo não cabe: abre na tabela até o estudante escolher o contrário. */
const estreita = window.matchMedia('(max-width: 600px)');
const emTabela = () => (S.tgTabela == null ? estreita.matches : S.tgTabela);

function aplicarModo() {
  const tab = emTabela();
  el('tgCanvas').hidden = tab;
  el('tgTab').hidden = !tab;
  el('tgTabela').textContent = tab ? 'Ver como grafo' : 'Ver como tabela';
}

export function renderGrafoTrilha() {
  const T = S.trilha;
  const painel = el('tgCanvas').closest('section');
  const comps = T ? montar(T) : [];
  painel.hidden = !T || !T.passos.length || !comps.length;
  if (painel.hidden) return;
  el('tgCanvas').innerHTML = desenhar(T, comps);
  el('tgTab').innerHTML = tabela(T);
  ligarDestaque(el('tgCanvas').querySelector('svg'));
  aplicarModo();
}

export function initGrafoTrilha() {
  el('tgTabela').addEventListener('click', () => { S.tgTabela = !emTabela(); aplicarModo(); });
  estreita.addEventListener('change', () => { if (S.tgTabela == null) aplicarModo(); });
}
