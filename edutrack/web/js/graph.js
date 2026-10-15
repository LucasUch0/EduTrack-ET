// Rede disciplina ↔ competência (RF22), com a mesma informação em tabela (RNF11) e forma além da cor (RNF13).
// Ligações contínuas: arestas "ensina" das ementas. Tracejadas: disciplina de apoio sugerida pela GNN.

import { CATEGORIAS, habilidades, sugestoes } from './dados.js';
import { GRADE, DX, HX, codTxt } from './catalog.js';
import { S } from './state.js';
import { esc, vazio } from './ui.js';
import { go } from './navigation.js';
import { closeOv } from './modal.js';
import { openDisc, openSkill } from './details.js';

const el = (id) => document.getElementById(id);
const corta = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

function montarRede() {
  const foco = S.graphFocus;
  let hs;
  let ds;
  if (foco) {
    const v = foco.slice(2);
    if (foco.charAt(0) === 'a') {
      const d = DX[v];
      hs = d.skills.map((s) => HX[s]).filter(Boolean);
      habilidades.forEach((h) => { if (h.disc === 0 && sugestoes[h.n] === d.cod && !hs.includes(h)) hs.push(h); });
      ds = [d];
    } else {
      const h = HX[v];
      hs = [h];
      ds = GRADE.filter((d) => d.skills.includes(h.n));
    }
    hs = hs.slice(0, 12);
    ds = ds.slice(0, 12);
  } else {
    const naCat = (h) => S.graphCat === 'todas' || h.cat === Number(S.graphCat);
    const porDemanda = (a, b) => b.vagas - a.vagas || a.n.localeCompare(b.n, 'pt-BR');
    hs = habilidades.filter((h) => h.vagas > 0 && naCat(h)).sort(porDemanda).slice(0, 9);
    // As lacunas mais pedidas que têm disciplina de apoio sugerida pela GNN entram na vista geral,
    // senão as ligações tracejadas só apareceriam com foco.
    hs = hs.concat(habilidades.filter((h) => h.vagas > 0 && h.disc === 0 && sugestoes[h.n] && naCat(h) && !hs.includes(h))
      .sort(porDemanda).slice(0, 3));
    const nomes = hs.map((h) => h.n);
    const apoio = new Set(hs.filter((h) => h.disc === 0 && sugestoes[h.n]).map((h) => sugestoes[h.n]));
    const grau = (d) => d.skills.filter((s) => nomes.includes(s)).length;
    ds = GRADE.filter((d) => grau(d) > 0 || apoio.has(d.cod))
      .sort((a, b) => Number(apoio.has(b.cod)) - Number(apoio.has(a.cod)) || grau(b) - grau(a) || a.periodo - b.periodo)
      .slice(0, 10);
  }
  const pred = [];
  hs.forEach((h) => {
    if (h.disc === 0 && sugestoes[h.n]) {
      const d = DX[sugestoes[h.n]];
      if (d) { pred.push({ a: d.cod, m: h.n }); if (!ds.includes(d)) ds.push(d); }
    }
  });
  // Ordena as disciplinas pela posição média das competências a que se ligam (menos cruzamentos).
  const pos = new Map(hs.map((h, i) => [h.n, i]));
  const centro = (d) => {
    const ys = d.skills.filter((s) => pos.has(s)).map((s) => pos.get(s))
      .concat(pred.filter((p) => p.a === d.cod).map((p) => pos.get(p.m)));
    return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : hs.length;
  };
  ds = ds.slice().sort((a, b) => centro(a) - centro(b) || a.periodo - b.periodo);
  return { hs, ds, pred, foco };
}

function ligacoes({ hs, ds, pred }) {
  const nomes = hs.map((h) => h.n);
  const codigos = ds.map((d) => d.cod);
  const lista = [];
  ds.forEach((d) => d.skills.forEach((s) => { if (nomes.includes(s)) lista.push({ a: d.cod, m: s, prevista: false }); }));
  if (S.graphPred) pred.forEach((p) => { if (codigos.includes(p.a) && nomes.includes(p.m)) lista.push({ a: p.a, m: p.m, prevista: true }); });
  return lista;
}

function renderDiagrama({ hs, ds }, arestas) {
  const W = 900; const rh = 56; const tp = 64; const xA = 250; const xM = 610;
  const H = tp + Math.max(ds.length, hs.length) * rh + 24;
  const pA = {};
  const pM = {};
  ds.forEach((d, i) => { pA[d.cod] = tp + i * rh; });
  hs.forEach((h, i) => { pM[h.n] = tp + i * rh; });

  const curva = (y1, y2) => `M${xA} ${y1} C ${xA + 130} ${y1}, ${xM - 130} ${y2}, ${xM} ${y2}`;
  const caminhos = arestas.map((l) => `<path class="ge${l.prevista ? ' pd' : ''}" data-a="${esc(l.a)}" data-m="${esc(l.m)}" d="${curva(pA[l.a], pM[l.m])}"/>`).join('');

  const nosDisc = ds.map((d) => {
    const y = pA[d.cod];
    return `<g class="gn ac" tabindex="0" role="button" data-n="a:${esc(d.cod)}" aria-label="Disciplina ${esc(d.nome)}, ${d.periodo}º período">`
      + `<circle class="gshape" cx="${xA}" cy="${y}" r="8"/>`
      + `<text x="${xA - 16}" y="${y - 1}" text-anchor="end">${esc(corta(d.nome, 34))}</text>`
      + `<text class="sb" x="${xA - 16}" y="${y + 13}" text-anchor="end">${d.periodo}º período${d.oficial ? '' : ' · ref.'}</text></g>`;
  }).join('');

  const nosComp = hs.map((h) => {
    const y = pM[h.n];
    const coberta = h.disc > 0;
    const forma = coberta
      ? `<circle class="gshape" cx="${xM}" cy="${y}" r="8"/>`
      : `<polygon class="gshape" points="${xM},${y - 10} ${xM + 10},${y} ${xM},${y + 10} ${xM - 10},${y}"/>`;
    return `<g class="gn ${coberta ? 'mc' : 'gp'}" tabindex="0" role="button" data-n="m:${esc(h.n)}" aria-label="Competência ${esc(h.n)}, ${h.vagas} vagas, ${coberta ? 'ensinada na grade' : 'sem disciplina na grade'}">`
      + forma
      + `<text x="${xM + 16}" y="${y - 1}">${esc(corta(h.n, 34))}</text>`
      + `<text class="sb" x="${xM + 16}" y="${y + 13}">${h.vagas} ${h.vagas === 1 ? 'vaga' : 'vagas'}${coberta ? '' : ' · sem disciplina'}</text></g>`;
  }).join('');

  const host = el('canvas');
  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="group" aria-label="Rede entre disciplinas e competências. Tab percorre os pontos e Enter abre os detalhes.">`
    + `<text class="col-t" x="${xA - 16}" y="32" text-anchor="end" aria-hidden="true">DISCIPLINAS</text>`
    + `<text class="col-t" x="${xM + 16}" y="32" aria-hidden="true">MERCADO</text>`
    + `<g aria-hidden="true">${caminhos}</g>${nosDisc}${nosComp}</svg>`;

  const svg = host.querySelector('svg');
  svg.querySelectorAll('.gn').forEach((node) => {
    const k = node.dataset.n;
    const isA = k.charAt(0) === 'a';
    const v = k.slice(2);
    const acender = () => {
      svg.querySelectorAll('.ge').forEach((ed) => {
        const m = isA ? ed.dataset.a === v : ed.dataset.m === v;
        ed.classList.toggle('hot', m);
        ed.classList.toggle('dim', !m);
      });
      svg.querySelectorAll('.gn').forEach((n2) => {
        if (n2 === node) { n2.classList.remove('dim'); return; }
        const v2 = n2.dataset.n.slice(2);
        const isA2 = n2.dataset.n.charAt(0) === 'a';
        let ligado = false;
        svg.querySelectorAll('.ge').forEach((ed) => {
          if (isA && !isA2 && ed.dataset.a === v && ed.dataset.m === v2) ligado = true;
          if (!isA && isA2 && ed.dataset.m === v && ed.dataset.a === v2) ligado = true;
        });
        n2.classList.toggle('dim', !ligado);
      });
    };
    const apagar = () => {
      svg.querySelectorAll('.ge').forEach((ed) => ed.classList.remove('hot', 'dim'));
      svg.querySelectorAll('.gn').forEach((n2) => n2.classList.remove('dim'));
    };
    node.addEventListener('mouseenter', acender);
    node.addEventListener('focus', acender);
    node.addEventListener('mouseleave', apagar);
    node.addEventListener('blur', apagar);
    const abrir = () => (isA ? openDisc(v) : openSkill(v));
    node.addEventListener('click', abrir);
    node.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abrir(); } });
  });
}

function renderTabela({ hs }, arestas) {
  const linhas = arestas.slice()
    .sort((x, y) => DX[x.a].nome.localeCompare(DX[y.a].nome, 'pt-BR') || x.m.localeCompare(y.m, 'pt-BR'))
    .map((l) => {
      const d = DX[l.a];
      const h = HX[l.m];
      return `<tr><td style="font-weight:600">${esc(d.nome)}<span class="cd-sub mono">${esc(codTxt(d))} · ${d.periodo}º período</span></td>`
        + `<td>${esc(h.n)}</td><td class="mono">${h.vagas}</td>`
        + `<td>${l.prevista ? '<span class="tag tag-sky">Sugestão da GNN</span>' : '<span class="tag tag-slate">Ensinada na ementa</span>'}</td></tr>`;
    });
  const ligadas = new Set(arestas.map((l) => l.m));
  hs.filter((h) => !ligadas.has(h.n)).forEach((h) => {
    linhas.push(`<tr><td style="color:var(--ink-3)">—</td><td>${esc(h.n)}</td><td class="mono">${h.vagas}</td><td><span class="tag tag-rose">Sem ligação com a grade</span></td></tr>`);
  });
  el('graphTable').innerHTML = '<table class="tbl"><caption class="sr">Mesma informação da rede: cada ligação entre disciplina e competência.</caption>'
    + '<thead><tr><th scope="col">Disciplina</th><th scope="col">Competência</th><th scope="col">Vagas</th><th scope="col">Ligação</th></tr></thead>'
    + `<tbody>${linhas.join('')}</tbody></table>`;
}

export function drawGraph() {
  const rede = montarRede();
  if (!rede.hs.length || !rede.ds.length) {
    const aviso = vazio('info', 'Nada para mostrar aqui', 'Nenhuma disciplina da grade se liga a este ponto. Escolha outra categoria ou outro foco.');
    el('canvas').innerHTML = aviso;
    el('graphTable').innerHTML = aviso;
    el('gstats').innerHTML = '';
    return;
  }
  const arestas = ligacoes(rede);
  renderDiagrama(rede, arestas);
  renderTabela(rede, arestas);

  const nObs = arestas.filter((l) => !l.prevista).length;
  const foco = rede.foco;
  el('gstats').innerHTML = (foco ? `<span>Foco: <b>${esc(foco.charAt(0) === 'a' ? DX[foco.slice(2)].nome : foco.slice(2))}</b> <button class="linkbtn" data-foco="">remover foco</button></span>` : '')
    + `<span>Pontos: <b>${rede.ds.length + rede.hs.length}</b></span>`
    + `<span>Ensinadas na ementa: <b>${nObs}</b></span>`
    + `<span>Sugestões da GNN: <b>${arestas.length - nObs}</b></span>`;
}

function focarGrafo(valor) {
  S.graphFocus = valor || '';
  el('graphFocus').value = S.graphFocus;
  el('graphCat').disabled = !!S.graphFocus;
  drawGraph();
}

function aplicarModo() {
  el('canvas').hidden = S.graphTabela;
  el('graphTable').hidden = !S.graphTabela;
  el('tableBtn').setAttribute('aria-pressed', String(S.graphTabela));
}

export function initGraph() {
  const cat = el('graphCat');
  CATEGORIAS.forEach((c, i) => {
    const o = document.createElement('option');
    o.value = String(i);
    o.textContent = c;
    cat.appendChild(o);
  });
  cat.addEventListener('change', function () { S.graphCat = this.value; drawGraph(); });

  el('predBtn').addEventListener('click', function () {
    S.graphPred = !S.graphPred;
    this.setAttribute('aria-pressed', String(S.graphPred));
    drawGraph();
  });

  el('tableBtn').addEventListener('click', () => { S.graphTabela = !S.graphTabela; aplicarModo(); });

  const foco = el('graphFocus');
  foco.innerHTML = '<option value="">Rede completa (sem foco)</option>'
    + `<optgroup label="Centralizar em uma disciplina">${GRADE.map((d) => `<option value="a:${esc(d.cod)}">${esc(d.nome)} (${d.periodo}º)</option>`).join('')}</optgroup>`
    + `<optgroup label="Centralizar em uma competência">${habilidades.slice().sort((a, b) => a.n.localeCompare(b.n, 'pt-BR')).map((h) => `<option value="m:${esc(h.n)}">${esc(h.n)}</option>`).join('')}</optgroup>`;
  foco.addEventListener('change', function () { focarGrafo(this.value); });

  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-foco]');
    if (!b) return;
    const ov = el('ovInfo');
    if (ov.classList.contains('open')) closeOv(ov);
    if (S.view !== 'sobre') go('sobre');
    el('redeCompleta').open = true;
    focarGrafo(b.dataset.foco);
    el(S.graphTabela ? 'graphTable' : 'canvas').scrollIntoView({ block: 'center' });
  });

  // a rede completa fica recolhida em Sobre: só é desenhada quando alguém a abre
  el('redeCompleta').addEventListener('toggle', (e) => { if (e.target.open) drawGraph(); });

  aplicarModo();
}
