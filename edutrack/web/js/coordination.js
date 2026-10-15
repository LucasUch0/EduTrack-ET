// Coordenação e NDE — diagnóstico curricular do curso calculado pelo serviço (RF32–RF35, RN08).

import { HX, DX } from './catalog.js';
import { PERFIS } from './config.js';
import { S } from './state.js';
import { severidade } from './analysis.js';
import { pedirDiagnostico, urlDiagnosticoCsv } from './servico.js';
import { openSkill } from './details.js';
import { tornarAcionavel } from './accessibility.js';
import { esc, kpi, vazio, toast, pct } from './ui.js';

const el = (id) => document.getElementById(id);
const ROTULO = { danger: 'Alta', warn: 'Média', info: 'Baixa' };
const SELO = { danger: 'tag-rose', warn: 'tag-amber', info: 'tag-sky' };
let pedido = 0;
const INICIAIS = 10;
let todasLacunas = false;

export async function renderCoord() {
  const meu = ++pedido;
  el('coKpis').setAttribute('aria-busy', 'true');
  let D;
  try {
    D = (await pedirDiagnostico(S.coPerfil)).dados;
  } catch (e) {
    if (meu === pedido) {
      el('coKpis').innerHTML = '';
      el('coGaps').innerHTML = vazio('bad', 'Não foi possível carregar o diagnóstico', e.message);
      el('coCats').innerHTML = '';
      el('coSemDem').innerHTML = '';
    }
    return;
  } finally {
    if (meu === pedido) el('coKpis').setAttribute('aria-busy', 'false');
  }
  if (meu !== pedido) return;

  el('coKpis').innerHTML = [
    { v: D.habilidades_demandadas, l: 'Competências pedidas pelas vagas', s: `nas ${D.vagas_consideradas} vagas consideradas` },
    { v: D.lacunas.length, l: 'Não ensinadas no curso', s: 'nenhuma disciplina da grade ensina' },
    { v: pct(D.cobertura_da_demanda), l: 'Cobertura do mercado pelo curso', s: 'do que as vagas pedem, o curso ensina isso' }
  ].map(kpi).join('');

  el('coGaps').innerHTML = D.lacunas.length
    ? '<table class="tbl"><caption class="sr">Competências pedidas pelas vagas e não ensinadas no curso</caption><thead><tr><th scope="col">#</th><th scope="col">Competência</th><th scope="col">Pedida em</th><th scope="col">Prioridade</th><th scope="col">Disciplina mais próxima (sugestão da IA)</th></tr></thead><tbody>'
      + D.lacunas.slice(0, todasLacunas ? undefined : INICIAIS).map((x, i) => {
        const sv = severidade(x.demanda);
        const ponte = x.ponte && x.ponte[0];
        return `<tr class="clk" data-sk="${esc(x.nome)}"><td class="mono">${i + 1}</td>`
          + `<td style="font-weight:600">${esc(x.nome)}<span class="cd-sub">${esc(x.categoria)}</span></td>`
          + `<td class="mono">${x.vagas} ${x.vagas === 1 ? 'vaga' : 'vagas'} (${pct(x.demanda)})</td>`
          + `<td><span class="tag ${SELO[sv]}">${ROTULO[sv]}</span></td>`
          + `<td style="color:var(--ink-2)">${x.disciplina_mais_proxima
            ? `${esc(x.disciplina_mais_proxima)}${ponte ? `<span class="cd-sub">ensina ${esc(ponte.nome)}, que as vagas pedem junto (${ponte.vagas} vagas)</span>` : ''}`
            : '<span style="color:var(--ink-3)" aria-hidden="true">—</span><span class="sr">sem sugestão com evidência suficiente</span>'}</td></tr>`;
      }).join('')
      + '</tbody></table>'
      + (D.lacunas.length > INICIAIS ? `<div class="mais" style="padding:12px 24px 0"><button type="button" class="btn btn-line btn-sm" id="coMais">${todasLacunas ? 'Mostrar só as 10 primeiras' : `Mostrar todas (${D.lacunas.length})`}</button></div>` : '')
      + '<p class="nota-fina" style="padding:0 24px 18px">Disciplina mais próxima: sugestão da rede neural de grafos, mostrada só quando a disciplina ensina algo que as vagas pedem junto com a competência em ao menos duas vagas; “—” quando não há indício suficiente. Ainda não validada por professores.</p>'
    : vazio('ok', 'Nenhuma lacuna institucional', 'Toda competência pedida pelas vagas tem ao menos uma disciplina que a ensina.');

  el('coCats').innerHTML = D.por_categoria.length
    ? '<table class="tbl"><caption class="sr">Cobertura por área</caption><thead><tr><th scope="col">Área</th><th scope="col">Pedidas pelas vagas</th><th scope="col">Ensinadas no curso</th><th scope="col">Cobertura</th></tr></thead><tbody>'
      + D.por_categoria.map((c) => {
        const p = c.demandadas ? c.cobertas / c.demandadas : 0;
        return `<tr><td>${esc(c.categoria)}</td><td class="mono">${c.demandadas}</td><td class="mono">${c.cobertas}</td>`
          + `<td><div class="bar-row" style="padding:0"><div class="track" role="img" aria-label="${pct(p)}"><div class="fill ${p >= 0.6 ? 'mint' : (p >= 0.3 ? 'amber' : 'rose')}" style="width:${Math.round(p * 100)}%"></div></div><span class="vv">${pct(p)}</span></div></td></tr>`;
      }).join('')
      + '</tbody></table>'
    : '';

  el('coSemDem').innerHTML = D.ensinadas_sem_demanda.length
    ? '<table class="tbl"><caption class="sr">Competências ensinadas sem demanda nas vagas</caption><thead><tr><th scope="col">Competência</th><th scope="col">Área</th><th scope="col">Disciplinas que ensinam</th></tr></thead><tbody>'
      + D.ensinadas_sem_demanda.map((x) => {
        const h = HX[x.nome];
        return `<tr class="clk" data-sk="${esc(x.nome)}"><td style="font-weight:600">${esc(x.nome)}</td><td style="color:var(--ink-3)">${esc(h ? h.catNome : '')}</td>`
          + `<td style="color:var(--ink-2)">${esc(h ? h.discs.map((c) => DX[c].nome).join(', ') : '')}</td></tr>`;
      }).join('')
      + '</tbody></table>'
    : vazio('info', 'Nada por aqui', 'Toda competência ensinada aparece em ao menos uma vaga desta área.');

  el('coMais')?.addEventListener('click', () => { todasLacunas = !todasLacunas; renderCoord(); });
  document.querySelectorAll('#v-coordenacao [data-sk]').forEach((tr) => tornarAcionavel(tr, () => openSkill(tr.dataset.sk)));
}

function exportarCsv() {
  const a = document.createElement('a');
  a.href = urlDiagnosticoCsv(S.coPerfil);
  a.download = `diagnostico_curricular_${S.coPerfil}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast('ok', 'Diagnóstico exportado', 'CSV gerado pelo serviço, com separador ";" para abrir no Excel.');
}

export function initCoordination() {
  const area = el('coArea');
  area.innerHTML = Object.entries(PERFIS).map(([k, p]) => `<option value="${k}">${esc(p.t)} (${p.vagas} vagas)</option>`).join('');
  area.value = S.coPerfil;
  area.addEventListener('change', function () { S.coPerfil = this.value; renderCoord(); });
  el('coCsv').addEventListener('click', exportarCsv);
}
