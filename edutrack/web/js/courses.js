// Etapa 1 — disciplinas concluídas. Continuidade entre sessões por arquivo do próprio usuário (RF31a).

import { disciplinas } from './dados.js';
import { GRADE, PERIODOS, codTxt, nomesPre } from './catalog.js';
import { PPC, PERFIS, K_OPCOES, MODELOS, ARQUIVO_SELECAO } from './config.js';
import { S, salvarProgresso } from './state.js';
import { esc, toast } from './ui.js';
import { baixar, hojeArq } from './export.js';
import { confirmar } from './modal.js';
import { go, syncLocks } from './navigation.js';
import { renderDiagnostico } from './diagnostic.js';
import { renderMercado } from './market.js';
import { exibirPainelTrilha, syncOpcoesTrilha } from './recommendations.js';

const el = (id) => document.getElementById(id);

/** Períodos abertos pelo estudante; sobrevive às re-renderizações da grade. */
const abertos = new Set();
let busca = '';

const semAcento = (t) => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

export function renderPicks() {
  const q = semAcento(busca.trim());
  const primeiro = PERIODOS.find((p) => PPC.periodosProcessados.includes(p));
  el('pickHost').innerHTML = PERIODOS.map((p) => {
    const todas = disciplinas.filter((d) => d.periodo === p);
    const ds = q ? todas.filter((d) => semAcento(`${d.nome} ${codTxt(d)}`).includes(q)) : todas;
    if (!ds.length) return '';
    const stub = !PPC.periodosProcessados.includes(p);
    const marcadas = stub ? 0 : todas.filter((d) => S.picks.includes(d.cod)).length;
    const aberto = q || abertos.has(p) || (!abertos.size && (p === primeiro || marcadas > 0));
    const itens = ds.map((d) => {
      const on = !stub && S.picks.includes(d.cod);
      // código e carga horária não ajudam a reconhecer a disciplina (H6): só o pré-requisito, se houver
      const pre = d.pre.length ? `Requer ${nomesPre(d).join(', ')}` : '';
      return `<label class="pick${on ? ' on' : ''}${stub ? ' stub' : ''}"${stub ? ' title="Período ainda não incluído no EduTrack: não entra na análise"' : ''}>`
        + `<input type="checkbox" value="${esc(d.cod)}"${on ? ' checked' : ''}${stub ? ' disabled' : ''}>`
        + `<span>${esc(d.nome)}${pre ? `<span class="cd">${esc(pre)}</span>` : ''}</span></label>`;
    }).join('');
    const tudo = marcadas === todas.length;
    const resumo = stub
      ? '<span class="tag tag-slate">ainda não incluído</span>'
      : `<span class="per-n${marcadas ? ' on' : ''}">${marcadas}/${todas.length}</span>`;
    return `<details class="per-group" data-per="${p}"${aberto ? ' open' : ''}>`
      + `<summary><span class="per-t">${p}º período</span>${resumo}<span class="fold-ic" aria-hidden="true"></span></summary>`
      + (stub || q ? '' : `<button type="button" class="linkbtn per-all" data-per-all="${p}">${tudo ? 'Desmarcar' : 'Marcar'} todas do ${p}º período</button>`)
      + `<div class="pick-grid">${itens}</div></details>`;
  }).join('') || '<p class="nota-fina" style="margin:0">Nenhuma disciplina encontrada para essa busca.</p>';
  syncPickCount();
}

/** Na primeira interação, guarda os períodos que abriram por padrão para não fechá-los. */
function lembrarAbertos() {
  if (abertos.size || busca.trim()) return;
  el('pickHost').querySelectorAll('.per-group[open]').forEach((x) => abertos.add(Number(x.dataset.per)));
}

/** Atualiza contador e botão "Marcar todas" de um período sem refazer a grade (o foco fica onde está). */
function syncPeriodo(grupo) {
  const p = Number(grupo.dataset.per);
  const cods = GRADE.filter((d) => d.periodo === p).map((d) => d.cod);
  const marcadas = cods.filter((c) => S.picks.includes(c)).length;
  const n = grupo.querySelector('.per-n');
  if (n) { n.textContent = `${marcadas}/${cods.length}`; n.classList.toggle('on', marcadas > 0); }
  const b = grupo.querySelector('.per-all');
  if (b) b.textContent = `${marcadas === cods.length ? 'Desmarcar' : 'Marcar'} todas do ${p}º período`;
}

function syncPickCount() {
  const n = S.picks.length;
  el('pickCount').textContent = n ? `${n} ${n === 1 ? 'disciplina marcada' : 'disciplinas marcadas'}` : 'Nenhuma disciplina marcada';
  el('btnAnalisar').disabled = n === 0;
  el('btnExportarSel').disabled = n === 0;
}

/** Mantém diagnóstico e mercado coerentes com o que está marcado agora. */
function picksMudaram() {
  if (S.analisado && !S.picks.length) { S.analisado = false; syncLocks(); }
  if (S.analisado) { renderDiagnostico(); renderMercado(); }
  salvarProgresso();
}

function limparTudo(codigos = []) {
  S.picks = codigos;
  S.analisado = false;
  S.trilhaFeita = false;
  S.trilha = null;
  renderPicks();
  syncLocks();
  exibirPainelTrilha(false);
  salvarProgresso({ trilhaSalvaEm: null });
}

function exportarSelecao() {
  if (!S.picks.length) return;
  const arquivo = {
    formato: ARQUIVO_SELECAO.formato,
    versao: ARQUIVO_SELECAO.versao,
    ppc: PPC.codigo,
    exportado_em: new Date().toISOString(),
    disciplinas: S.picks.slice(),
    nomes: S.picks.map((c) => (GRADE.find((d) => d.cod === c) || {}).nome || c),
    trilha: { k: S.k, perfil: S.perfil, modelo: S.modelo }
  };
  baixar(`selecao-edutrack-${hojeArq()}.json`, JSON.stringify(arquivo, null, 2), 'application/json');
  toast('ok', 'Seleção exportada', 'Guarde o arquivo e importe-o quando voltar. Ele foi gerado no seu navegador; nada foi enviado ao servidor.');
}

async function importarSelecao(arquivo) {
  let dados = null;
  try { dados = JSON.parse(await arquivo.text()); } catch { /* tratado abaixo */ }
  const valido = dados && Array.isArray(dados.disciplinas) && (!dados.formato || dados.formato === ARQUIVO_SELECAO.formato);
  if (!valido) {
    toast('bad', 'Arquivo não reconhecido', 'Escolha um arquivo .json gerado em "Salvar arquivo".');
    return;
  }
  const lidos = [...new Set(dados.disciplinas.map(String))];
  const codigos = lidos.filter((c) => GRADE.some((d) => d.cod === c));
  if (!codigos.length) {
    toast('warn', 'Nenhuma disciplina reconhecida', 'Os códigos do arquivo não correspondem à grade atual.');
    return;
  }
  const ignorados = lidos.length - codigos.length;
  const outroPpc = dados.ppc && dados.ppc !== PPC.codigo;

  const aplicar = () => {
    if (dados.trilha && K_OPCOES.includes(dados.trilha.k)) S.k = dados.trilha.k;
    if (dados.trilha && PERFIS[dados.trilha.perfil]) S.perfil = dados.trilha.perfil;
    if (dados.trilha && MODELOS[dados.trilha.modelo]) S.modelo = dados.trilha.modelo;
    syncOpcoesTrilha();
    limparTudo(codigos);
    const partes = [`${codigos.length} disciplina(s) restaurada(s).`];
    if (ignorados) partes.push(`${ignorados} código(s) fora da grade foram ignorados.`);
    if (outroPpc) partes.push(`O arquivo é do PPC ${dados.ppc}; a grade atual é ${PPC.codigo}.`);
    partes.push('Clique em "Ver o que falta" para ver o resultado.');
    toast(ignorados || outroPpc ? 'warn' : 'ok', 'Seleção importada', partes.join(' '), 7000);
  };

  if (!S.picks.length) { aplicar(); return; }
  confirmar('Substituir a seleção atual?',
    `<p style="color:var(--ink-2);font-size:.9375rem">Você tem ${S.picks.length} disciplina(s) marcada(s) e o arquivo traz ${codigos.length}. A seleção e a trilha desta sessão serão substituídas.</p>`,
    aplicar, 'Substituir');
}

export function initCourses() {
  el('pickHost').addEventListener('change', (e) => {
    const input = e.target;
    if (!input.matches('input[type="checkbox"]')) return;
    const ix = S.picks.indexOf(input.value);
    if (input.checked && ix === -1) S.picks.push(input.value);
    if (!input.checked && ix !== -1) S.picks.splice(ix, 1);
    input.closest('.pick').classList.toggle('on', input.checked);
    const grupo = input.closest('.per-group');
    lembrarAbertos();
    if (grupo && !busca.trim()) abertos.add(Number(grupo.dataset.per));
    if (grupo) syncPeriodo(grupo);
    syncPickCount();
    picksMudaram();
  });

  el('pickHost').addEventListener('click', (e) => {
    const b = e.target.closest('[data-per-all]');
    if (!b) return;
    const p = Number(b.dataset.perAll);
    const cods = GRADE.filter((d) => d.periodo === p).map((d) => d.cod);
    const tudo = cods.every((c) => S.picks.includes(c));
    lembrarAbertos();
    S.picks = tudo ? S.picks.filter((c) => !cods.includes(c)) : [...new Set([...S.picks, ...cods])];
    abertos.add(p);
    renderPicks();
    el('pickHost').querySelector(`[data-per-all="${p}"]`)?.focus();
    picksMudaram();
  });

  // lembra quais períodos o estudante abriu ou fechou
  el('pickHost').addEventListener('toggle', (e) => {
    const g = e.target;
    if (!g.matches || !g.matches('.per-group') || busca.trim()) return;
    lembrarAbertos();
    if (g.open) abertos.add(Number(g.dataset.per)); else abertos.delete(Number(g.dataset.per));
  }, true);

  el('pickSearch').addEventListener('input', (e) => { busca = e.target.value; renderPicks(); });

  // atalho para quem está no meio do curso: marca todos os períodos até o escolhido (desfazível)
  const ate = el('ateSel');
  ate.insertAdjacentHTML('beforeend', PERIODOS.filter((p) => PPC.periodosProcessados.includes(p))
    .map((p) => `<option value="${p}">${p}º período</option>`).join(''));
  ate.addEventListener('change', () => {
    const n = Number(ate.value);
    ate.value = '';
    if (!n) return;
    const antes = S.picks.slice();
    const cods = GRADE.filter((d) => d.periodo <= n && PPC.periodosProcessados.includes(d.periodo)).map((d) => d.cod);
    S.picks = [...new Set([...S.picks, ...cods])];
    const novas = S.picks.length - antes.length;
    abertos.clear();
    renderPicks();
    picksMudaram();
    toast('ok', `Marcadas até o ${n}º período`,
      novas ? `${novas} ${novas === 1 ? 'disciplina marcada' : 'disciplinas marcadas'}. Desmarque as que você ainda não concluiu.` : 'Todas já estavam marcadas.',
      7000, novas ? {
        rotulo: 'Desfazer',
        fn: () => { S.picks = antes; renderPicks(); picksMudaram(); }
      } : undefined);
  });

  // apagar é fácil de desfazer: o aviso traz "Desfazer" em vez de um diálogo de confirmação (H5)
  el('btnLimpar').addEventListener('click', () => {
    if (!S.picks.length) return;
    const antes = { picks: S.picks.slice(), analisado: S.analisado, trilha: S.trilha, chave: S.trilhaChave };
    limparTudo();
    toast('info', 'Seleção apagada', `${antes.picks.length} ${antes.picks.length === 1 ? 'disciplina desmarcada' : 'disciplinas desmarcadas'}.`, 8000, {
      rotulo: 'Desfazer',
      fn: () => {
        S.picks = antes.picks;
        S.analisado = antes.analisado;
        S.trilha = antes.trilha;
        S.trilhaChave = antes.chave;
        renderPicks();
        syncLocks();
        if (S.trilha) exibirPainelTrilha(true);
        salvarProgresso(S.trilha ? { trilhaSalvaEm: new Date().toISOString() } : undefined);
      }
    });
  });

  el('btnAnalisar').addEventListener('click', () => {
    S.analisado = true;
    salvarProgresso();
    syncLocks();
    renderDiagnostico();
    renderMercado();
    go('diagnostico');
  });

  el('btnExportarSel').addEventListener('click', exportarSelecao);

  const entrada = el('inputSelecao');
  el('btnImportarSel').addEventListener('click', () => entrada.click());
  entrada.addEventListener('change', () => {
    const [arquivo] = entrada.files;
    entrada.value = '';
    if (arquivo) importarSelecao(arquivo);
  });
}
