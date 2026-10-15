// Etapa 3 — trilha formativa calculada pelo serviço: geração, resultado e exportação (RF29–RF31, RF36, RF37).

import { DX } from './catalog.js';
import { PPC, COLETA, METRICAS, PERFIS, MODELOS, K_PADRAO, modeloEfetivo } from './config.js';
import { S, salvarProgresso } from './state.js';
import { pedirTrilha } from './servico.js';
import { go } from './navigation.js';
import { esc, br, dataCurta, toast, vazio, pct, num } from './ui.js';
import { openDisc, openSkill } from './details.js';
import { tornarAcionavel } from './accessibility.js';
import { baixar, paraCsv, hojeArq } from './export.js';
import { renderGrafoTrilha, initGrafoTrilha } from './trailgraph.js';

const el = (id) => document.getElementById(id);

/** "de todas as vagas" ou "das vagas de desenvolvimento de software", preservando siglas (TI, IA). */
function alvoDaDemanda(T) {
  if (T.perfil === 'todos' || !T.perfilNome) return 'de todas as vagas';
  const nome = T.perfilNome.split(' ').map((w) => (w.length > 1 && w === w.toUpperCase() ? w : w.toLowerCase())).join(' ');
  return `das vagas de ${nome}`;
}

export function syncOpcoesTrilha() {
  el('perfilSel').value = S.perfil;
  el('modeloPills').querySelectorAll('.pill').forEach((p) => p.setAttribute('aria-pressed', String(p.dataset.modelo === S.modelo)));
  el('kSel').value = String(S.k);
}

/** Mostra só um dos estados da trilha: calculando, resultado ou erro. */
function mostrar(estado) {
  el('triProc').hidden = estado !== 'proc';
  el('triRes').hidden = estado !== 'res';
  el('triErro').hidden = estado !== 'erro';
}

/** Com resultado na mão, exibe-o; sem ele, esconde tudo até a próxima geração. */
export function exibirPainelTrilha(comResultado) {
  mostrar(comResultado ? 'res' : null);
}

/** Converte a resposta do serviço para o formato das telas. */
function deResposta(r, ms, msServidor, modelo) {
  return {
    k: r.k, perfil: r.perfil, perfilNome: r.perfil_nome, vagas: r.vagas_consideradas,
    modelo, modeloUsado: r.modelo_afinidade,
    antes: r.aderencia_antes, depois: r.aderencia_depois, teto: r.aderencia_teto_curricular,
    passos: r.trilha.map((it) => ({
      d: DX[it.disciplina] || { cod: it.disciplina, nome: it.nome, periodo: it.periodo, pre: it.pre_requisitos },
      novas: it.habilidades_cobertas,
      ganho: it.ganho_aderencia,
      motivo: it.motivo,
      latentes: (it.afinidades_latentes || []).filter((a) => a.afinidade >= 0.2),
      pre: it.pre_requisitos
    })),
    complementares: r.habilidades_complementares.map((c) => ({ nome: c.nome, id: c.id, demanda: c.demanda, categoria: c.categoria, apoio: c.disciplina_base })),
    ms, msServidor,
    geradaEm: new Date().toISOString()
  };
}

function metricasDoModelo(chave, k) {
  const m = (METRICAS.cenarios || {}).texto_mascarado || {};
  const x = m[chave];
  if (!x || !x[`P@${k}`]) return null;
  return { p: x[`P@${k}`].media, r: x[`R@${k}`].media, nome: x.nome };
}

export function renderTrilha() {
  const T = S.trilha;
  if (!T) return;
  const efetivo = T.modeloUsado || modeloEfetivo(T.modelo);
  const outro = efetivo === 'gnn' ? 'tfidf' : 'gnn';
  const m = metricasDoModelo(efetivo, T.k);
  const mo = metricasDoModelo(outro, T.k);

  el('triTempo').textContent = `${T.msServidor != null ? (T.msServidor < 1 ? '< 1' : Math.round(T.msServidor)) : Math.round(T.ms)} ms`;
  const metodo = T.modelo === 'auto' ? '' : ` Escolhidas pela ${MODELOS[T.modelo] ? MODELOS[T.modelo].curto : efetivo}.`;
  el('triSub').textContent = `As disciplinas que mais aproximam você ${alvoDaDemanda(T)}, na ordem em que dá para cursá-las.${metodo}`;
  const n = T.passos.length;
  el('resTit').textContent = n
    ? `Com ${n === 1 ? 'esta disciplina' : `estas ${n} disciplinas`}, sua cobertura do mercado vai de ${pct(T.antes)} para ${pct(T.depois)}`
    : 'Nenhuma disciplina do curso cobre o que falta para esta área';
  el('resM').textContent = `Cobertura é quanto do que ${T.vagas} vagas pedem você já sabe. Cursando o curso inteiro, o máximo é ${pct(T.teto)}.`;

  // uma barra só, em camadas: hoje ⊂ depois da trilha ⊂ máximo com o curso todo
  const w = (v) => `${Math.round(v * 100)}%`;
  el('aderHost').innerHTML = `<div class="ader-bar" role="img" aria-label="Cobertura do mercado: hoje ${pct(T.antes)}, depois da trilha ${pct(T.depois)}, máximo com o curso todo ${pct(T.teto)}">`
      + `<span class="lv teto" style="width:${w(T.teto)}"></span><span class="lv dep" style="width:${w(T.depois)}"></span><span class="lv ant" style="width:${w(T.antes)}"></span></div>`
    + '<div class="ader-leg" aria-hidden="true">'
      + `<span><i class="ant"></i>Hoje <b>${pct(T.antes)}</b></span>`
      + `<span><i class="dep"></i>Depois da trilha <b>${pct(T.depois)}</b></span>`
      + `<span><i class="teto"></i>Máximo com o curso todo <b>${pct(T.teto)}</b></span></div>`;

  // cobertura acumulada a cada passo: o estudante vê o número subir, sem precisar somar pontos
  let acumulada = T.antes;
  const maior = n ? Math.max(...T.passos.map((p) => p.ganho)) : 0;
  el('rank').innerHTML = n ? T.passos.map((p, i) => {
    const d = p.d;
    acumulada += p.ganho;
    const porque = p.novas.length
      ? `Você aprende: ${p.novas.map((h) => h.nome).join(', ')}.`
      : `É ${p.motivo}.`;
    const pre = p.pre.length
      ? `<div class="pre">Pré-requisito: ${esc(p.pre.map((c) => {
        const passo = T.passos.findIndex((x) => x.d.cod === c);
        return (DX[c] ? DX[c].nome : c) + (S.picks.includes(c) ? ' (você já fez)' : (passo >= 0 ? ` (passo ${passo + 1})` : ''));
      }).join(', '))}</div>`
      : '';
    const destaque = p.ganho === maior && p.ganho > 0 && n > 1 ? ' <span class="tag tag-mint">maior impacto</span>' : '';
    return `<div class="rk rk-clk" role="button" data-disc="${esc(d.cod)}" aria-label="${esc(`Passo ${i + 1}: ${d.nome}, ${d.periodo}º período. ${porque} Sua cobertura vai a ${pct(acumulada)}. Abrir detalhes.`)}"><span class="ps">${i + 1}</span>`
      + `<div><div class="nm2">${esc(d.nome)} <span class="per-lbl">${d.periodo}º período</span>${destaque}</div>`
      + `<div class="wy">${esc(porque)}</div>${pre}</div>`
      + `<div class="scb"><div class="n">${pct(acumulada)}</div><div class="t">sua cobertura</div></div></div>`;
  }).join('') : vazio('ok', 'Nada a recomendar no curso', 'As disciplinas que faltam não ensinam o que as vagas desta área pedem. Veja abaixo o que aprender por fora.');

  el('complHost').innerHTML = T.complementares.length
    ? '<div class="panel"><div class="panel-head"><div><h2>Não ensinadas no curso</h2><p>As vagas pedem, mas nenhuma disciplina ensina: vale aprender por fora (cursos, projetos, estágio)</p></div></div><div class="panel-body">'
      + T.complementares.slice(0, 5).map((c) => {
        const ap = c.apoio;
        return `<div class="rk rk-out rk-clk" role="button" data-sk="${esc(c.nome)}" aria-label="${esc(`${c.nome}: pedida em ${pct(c.demanda)} das vagas. Abrir detalhes.`)}">`
          + `<div><div class="nm2">${esc(c.nome)}</div>`
          + (ap ? `<div class="wy">A IA sugere começar por ${esc(ap.nome)} (sugestão ainda não validada por professores)</div>` : '')
          + '</div>'
          + `<div class="scb"><div class="n neutro">${pct(c.demanda)}</div><div class="t">das vagas pedem</div></div></div>`;
      }).join('')
      + '</div></div>'
    : '';
  document.querySelectorAll('#rank [data-disc]').forEach((r) => tornarAcionavel(r, () => openDisc(r.dataset.disc)));
  document.querySelectorAll('#complHost [data-sk]').forEach((r) => tornarAcionavel(r, () => openSkill(r.dataset.sk)));

  renderGrafoTrilha();

  // resposta simples primeiro; os números técnicos (exigidos pela avaliação do TCC) ficam abaixo
  const emDez = m ? Math.round(10 * m.r) : null;
  el('acertoHost').innerHTML = m
    ? `<p class="conf">Nos testes, a disciplina certa estava entre as ${T.k} sugeridas em <b>${emDez} de cada 10</b> casos.</p>`
      + '<p class="nota-fina">Como testamos: escondemos do sistema ligações já conhecidas entre disciplinas e competências e pedimos que ele as encontrasse de novo. A medida avalia o método, não a sua trilha em particular, e lembra que esta é uma sugestão estatística, não uma orientação profissional.</p>'
      + '<div class="res-m tecnico">'
      + `<span>Recall@${T.k}: <span class="mono">${num(m.r)}</span></span>`
      + `<span>Precision@${T.k}: <span class="mono">${num(m.p)}</span></span>`
      + (mo ? `<span>${esc(mo.nome)}: <span class="mono">${num(mo.r)} / ${num(mo.p)}</span></span>` : '')
      + '</div>'
      + `<p class="nota-fina">Método ${esc(m.nome)}, média de ${METRICAS.sorteios || 20} sorteios; coleta de ${dataCurta(COLETA.data)}. A precisão é baixa por construção: cada competência tem uma ou duas disciplinas certas entre as ${T.k} sugeridas.</p>`
    : `<p class="nota-fina">Resultados dos testes indisponíveis. Coleta de ${dataCurta(COLETA.data)}.</p>`;
}

function trilhaObjeto() {
  const T = S.trilha;
  const efetivo = T.modeloUsado || modeloEfetivo(T.modelo);
  const m = metricasDoModelo(efetivo, T.k);
  return {
    gerada_em: T.geradaEm, ppc: PPC.codigo, ultima_coleta: COLETA.data, area_vagas: T.perfilNome, vagas_consideradas: T.vagas,
    k: T.k, modelo_afinidade: efetivo,
    disciplinas_cursadas: S.picks.slice(),
    aderencia: { antes: T.antes, depois: T.depois, teto_curricular: T.teto },
    metricas_avaliacao: m ? { cenario: 'vínculos latentes', precision_at_k: m.p, recall_at_k: m.r } : null,
    trilha: T.passos.map((p, i) => ({
      ordem: i + 1, tipo: 'disciplina', id: p.d.cod, codigo: p.d.codigo || null, nome: p.d.nome, periodo: p.d.periodo,
      competencias_cobertas: p.novas.map((h) => h.nome), pre_requisitos: p.pre, ganho_aderencia: p.ganho
    })),
    estudo_complementar: T.complementares.map((c, i) => ({
      ordem: T.passos.length + i + 1, tipo: 'competencia', nome: c.nome, categoria: c.categoria, demanda: c.demanda,
      disciplina_de_apoio_gnn: c.apoio ? c.apoio.nome : null
    }))
  };
}

/** Assinatura do que define a trilha: mudou, recalcula. */
const chaveAtual = () => JSON.stringify([[...S.picks].sort(), S.perfil, S.k, S.modelo]);

/** Ao abrir a aba, mostra a trilha das escolhas atuais, calculando-a se preciso (sem botão "Gerar"). */
export function garantirTrilha() {
  if (S.trilha && S.trilhaChave === chaveAtual()) { mostrar('res'); return; }
  gerar();
}

let pedidoAtual = 0;

/** Pede a trilha ao serviço; com `silencioso`, restaura a trilha da sessão sem indicador de espera. */
export async function gerar(silencioso = false, avisar = false) {
  if (!S.picks.length) {
    toast('warn', 'Nenhuma disciplina selecionada', 'Marque ao menos uma disciplina na etapa 1.');
    go('perfil');
    return;
  }
  const meu = ++pedidoAtual;
  const chave = chaveAtual();
  // o indicador só aparece se a resposta demorar: evita piscar a tela em cálculos de milissegundos
  const espera = silencioso ? null : setTimeout(() => { if (meu === pedidoAtual) mostrar('proc'); }, 250);
  el('triRes').setAttribute('aria-busy', 'true');
  try {
    const { dados, ms, msServidor } = await pedirTrilha(S.picks, S.perfil, S.k, S.modelo);
    if (meu !== pedidoAtual) return;
    S.trilha = deResposta(dados, ms, msServidor, S.modelo);
    S.trilhaChave = chave;
    S.trilhaFeita = true;
    renderTrilha();
    mostrar('res');
    if (avisar) toast('ok', 'Trilha atualizada', `${PERFIS[S.perfil] ? PERFIS[S.perfil].t : 'Todas as vagas'} · ${S.k} ${S.k === 1 ? 'disciplina' : 'disciplinas'} · ${MODELOS[S.modelo].curto}.`, 3500);
    // a trilha fica na sessão automaticamente: some ao fechar a aba
    salvarProgresso({ trilhaSalvaEm: new Date().toISOString(), trilhaK: S.k, trilhaPerfil: S.perfil, trilhaModelo: S.modelo });
  } catch (e) {
    if (meu !== pedidoAtual) return;
    el('triErroBody').innerHTML = vazio('bad', 'Não foi possível gerar a trilha', e.message)
      + '<div style="text-align:center;margin-bottom:24px"><button class="btn btn-line" id="btnTentar">Tentar de novo</button></div>';
    mostrar('erro');
    el('btnTentar').addEventListener('click', () => gerar());
  } finally {
    clearTimeout(espera);
    el('triRes').removeAttribute('aria-busy');
  }
}

/** Trocar uma opção recalcula na hora e avisa (H1). */
function aoMudarOpcao() {
  syncOpcoesTrilha();
  if (S.view === 'trilha') gerar(false, true);
}

export function initRecommendations() {
  initGrafoTrilha();
  const ajustes = document.querySelector('.tri-adv');
  document.addEventListener('click', (e) => { if (ajustes.open && !ajustes.contains(e.target)) ajustes.open = false; });
  ajustes.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && ajustes.open) { ajustes.open = false; ajustes.querySelector('summary').focus(); }
  });
  const perfis = el('perfilSel');
  perfis.innerHTML = Object.keys(PERFIS).map((k) => `<option value="${k}">${esc(PERFIS[k].t)} (${PERFIS[k].vagas})</option>`).join('');
  perfis.value = S.perfil;
  perfis.addEventListener('change', () => { S.perfil = perfis.value; aoMudarOpcao(); });
  const modelos = el('modeloPills');
  modelos.innerHTML = ['auto', 'gnn'].map((k) => `<button class="pill pill-2l" data-modelo="${k}" aria-pressed="${k === S.modelo}">${esc(MODELOS[k].t)}<span class="pill-d">${esc(MODELOS[k].d)}</span></button>`).join('');
  modelos.addEventListener('click', (e) => {
    const p = e.target.closest('[data-modelo]');
    if (!p) return;
    S.modelo = p.dataset.modelo;
    aoMudarOpcao();
  });
  el('kSel').addEventListener('change', function () { S.k = parseInt(this.value, 10) || K_PADRAO; aoMudarOpcao(); });

  el('expJson').addEventListener('click', () => {
    if (!S.trilha) return;
    baixar(`trilha-edutrack-${hojeArq()}.json`, JSON.stringify(trilhaObjeto(), null, 2), 'application/json');
  });

  el('expCsv').addEventListener('click', () => {
    if (!S.trilha) return;
    const o = trilhaObjeto();
    const linhas = [['Ordem', 'Tipo', 'Disciplina ou competência', 'Período', 'O que você aprende', 'Pré-requisitos', 'Sua cobertura depois (%)']];
    let acum = o.aderencia.antes;
    o.trilha.forEach((t) => linhas.push([t.ordem, 'Disciplina', t.nome, `${t.periodo}º`, t.competencias_cobertas.join(', '), t.pre_requisitos.map((c) => (DX[c] ? DX[c].nome : c)).join(', '), br((100 * (acum += t.ganho_aderencia)).toFixed(0))]));
    o.estudo_complementar.forEach((c) => linhas.push([c.ordem, 'Aprender por fora', c.nome, '', c.categoria, c.disciplina_de_apoio_gnn ? `a IA sugere começar por ${c.disciplina_de_apoio_gnn}` : '', '']));
    linhas.push([]);
    linhas.push(['Vagas consideradas', o.area_vagas]);
    linhas.push(['Disciplinas na trilha', o.k]);
    linhas.push(['Método', o.modelo_afinidade]);
    linhas.push(['Cobertura hoje (%)', br(Math.round(100 * o.aderencia.antes))]);
    linhas.push(['Cobertura depois da trilha (%)', br(Math.round(100 * o.aderencia.depois))]);
    linhas.push(['Máximo com o curso todo (%)', br(Math.round(100 * o.aderencia.teto_curricular))]);
    linhas.push(['Última coleta', dataCurta(o.ultima_coleta)]);
    baixar(`trilha-edutrack-${hojeArq()}.csv`, paraCsv(linhas), 'text/csv;charset=utf-8');
  });
}
