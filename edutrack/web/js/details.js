// Ficha de disciplina e de competência, aberta pelas listas, tabelas e pelo grafo.

import { disciplinas, vagas, sugestoes, SUGESTOES_INFO } from './dados.js';
import { DX, HX, nomesPre } from './catalog.js';
import { S } from './state.js';
import { dominadas } from './analysis.js';
import { info } from './modal.js';
import { esc, chipCompetencia, pct } from './ui.js';

const rotulo = (texto, margem = 6) => `<div class="lbl" style="margin-bottom:${margem}px">${texto}</div>`;
const MAX_VARIACOES = 8;
const MAX_VAGAS = 12;

export function openDisc(cod) {
  const d = disciplinas.find((x) => x.cod === cod);
  if (!d) return;
  const dom = dominadas();
  const sub = [`${d.periodo}º período`, d.ch ? `${d.ch} horas` : null].filter(Boolean).join(' · ');
  const apoios = Object.entries(sugestoes).filter(([, c]) => c === d.cod).map(([n]) => n);
  info(d.nome, sub,
    '<div class="dgrid">'
      + `<div><div class="k">Você já fez</div><div class="v">${S.picks.includes(d.cod) ? 'Sim' : 'Não'}</div></div>`
      + `<div><div class="k">Pré-requisitos</div><div class="v">${d.pre.length ? esc(nomesPre(d).join(', ')) : 'Nenhum'}</div></div>`
    + '</div><hr class="sep">'
    + rotulo('O que ela ensina que as vagas pedem', 8)
    + (d.skills.length
      ? `<div class="chips">${d.skills.map((x) => chipCompetencia(x, dom.has(x))).join('')}</div>`
        + '<p style="color:var(--ink-3);font-size:.8125rem;margin-top:8px">✓ = você já tem, por outra disciplina que marcou.</p>'
      : '<p style="color:var(--ink-3);font-size:.875rem">Não reconhecemos no conteúdo desta disciplina nenhuma competência pedida pelas vagas. Pode ser limitação da leitura automática, não falta de conteúdo.</p>')
    + (apoios.length
      ? `<hr class="sep">${rotulo('A IA sugere esta disciplina como ponto de partida para', 8)}<div class="chips">${apoios.map((x) => `<span class="chip-s neutro">${esc(x)}</span>`).join('')}</div>`
        + '<p style="color:var(--ink-3);font-size:.8125rem;margin-top:8px">Nenhuma disciplina ensina essas competências; esta é a mais próxima. Sugestão ainda não validada por professores.</p>'
      : '')
    + '<hr class="sep">'
    + rotulo(d.oficial ? 'Conteúdo da disciplina (ementa)' : 'Conteúdo da disciplina (ementa provisória)')
    + `<p style="color:var(--ink-2);font-size:.9rem">${esc(d.ementa) || 'Conteúdo ainda não disponível.'}</p>`
    + (d.oficial ? '' : '<p style="color:var(--ink-3);font-size:.8125rem;margin-top:8px">O programa oficial desta disciplina ainda não foi anexado; usamos uma descrição provisória.</p>'));
}

export function openSkill(n) {
  const h = HX[n];
  if (!h) return;
  const vg = vagas.filter((v) => v.skills.includes(h.n));
  const apoio = sugestoes[h.n] ? DX[sugestoes[h.n]] : null;
  const ap = SUGESTOES_INFO[h.n];
  const variacoes = h.syn.slice(0, MAX_VARIACOES);
  const tem = dominadas().has(h.n);
  // primeiro a resposta que o estudante procura: onde aprender
  const onde = h.disc
    ? `${rotulo('Onde aprender no curso', 8)}<div class="chips">${h.discs.map((c) => `<span class="chip-s">${esc(DX[c].nome)}</span>`).join('')}</div>`
    : `${rotulo('Onde aprender', 8)}<p style="color:var(--ink-2);font-size:.9rem">Nenhuma disciplina do curso ensina. Vale aprender por fora: cursos, projetos ou estágio.</p>`
      + (apoio ? `<p style="color:var(--ink-2);font-size:.9rem;margin-top:8px">A IA sugere começar por <b>${esc(apoio.nome)}</b>${ap && ap.ponte && ap.ponte[0] ? `, que ensina ${esc(ap.ponte[0].nome)} (as vagas costumam pedir as duas juntas)` : ''}. Sugestão ainda não validada por professores.</p>` : '');
  info(h.n, h.catNome,
    '<div class="dgrid">'
      + `<div><div class="k">Pedida em</div><div class="v">${h.vagas} de ${vagas.length} vagas${vagas.length ? ` (${pct(h.vagas / vagas.length)})` : ''}</div></div>`
      + `<div><div class="k">Você já tem</div><div class="v">${S.analisado ? (tem ? 'Sim' : 'Ainda não') : 'Marque suas disciplinas para saber'}</div></div>`
    + '</div><hr class="sep">'
    + onde
    + (vg.length
      ? `<hr class="sep">${rotulo('Vagas que pedem', 8)}<ul style="font-size:.875rem;color:var(--ink-2);display:flex;flex-direction:column;gap:6px">${vg.slice(0, MAX_VAGAS).map((v) => `<li>${esc(v.cargo)} — ${esc(v.empresa)}</li>`).join('')}</ul>`
        + (vg.length > MAX_VAGAS ? `<p style="color:var(--ink-3);font-size:.8125rem;margin-top:6px">e mais ${vg.length - MAX_VAGAS} vagas (veja a aba Mercado).</p>` : '')
      : '')
    + '<hr class="sep">'
    + rotulo('Nos anúncios, também aparece como', 8)
    + `<div class="chips">${variacoes.map((v) => `<span class="chip-s neutro">${esc(v)}</span>`).join('')}`
    + (h.syn.length > variacoes.length ? `<span class="chip-s neutro">+${h.syn.length - variacoes.length}</span>` : '') + '</div>');
}
