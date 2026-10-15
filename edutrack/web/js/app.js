// Orquestração: espera os dados do serviço, liga as telas à navegação e restaura a sessão aberta.

import { ERRO_CARGA } from './dados.js';
import { GRADE } from './catalog.js';
import { K_OPCOES, K_PADRAO, PERFIS, MODELOS } from './config.js';
import { S, lerProgresso, descartarProgressoPersistente } from './state.js';
import { initTheme, initMotion } from './accessibility.js';
import { initModals } from './modal.js';
import { initNavigation, registerViewHooks, syncLocks, renderSheet, go, vistaDoEndereco } from './navigation.js';
import { initCourses, renderPicks } from './courses.js';
import { initDiagnostic, renderDiagnostico } from './diagnostic.js';
import { initMarket, renderMercado } from './market.js';
import { initGraph, drawGraph } from './graph.js';
import { initRecommendations, syncOpcoesTrilha, exibirPainelTrilha, gerar, garantirTrilha } from './recommendations.js';
import { initCoordination, renderCoord } from './coordination.js';
import { renderSobre } from './about.js';
import { esc, TI } from './ui.js';

function mostrarErroDeCarga(erro) {
  const main = document.getElementById('main');
  main.setAttribute('aria-busy', 'false');
  main.innerHTML = '<section class="view active" aria-labelledby="t-erro"><div class="panel"><div class="panel-body">'
    + `<div class="empty"><div class="ic">${TI.bad}</div><h3 id="t-erro">Não foi possível carregar os dados</h3>`
    + `<p>${esc(erro && erro.message ? erro.message : 'Erro desconhecido.')} Confira se a janela do iniciar.bat continua aberta e recarregue a página (F5).</p></div>`
    + '</div></div></section>';
}

function restaurarSessao() {
  const p = lerProgresso();
  S.picks = (p.picks || []).filter((c) => GRADE.some((d) => d.cod === c));
  S.analisado = !!p.analisado && S.picks.length > 0;
  S.k = K_OPCOES.includes(p.trilhaK) ? p.trilhaK : K_PADRAO;
  S.perfil = PERFIS[p.trilhaPerfil] ? p.trilhaPerfil : 'todos';
  S.modelo = MODELOS[p.trilhaModelo] ? p.trilhaModelo : 'auto';
  syncOpcoesTrilha();
  renderPicks();
  syncLocks();
  if (S.analisado) renderDiagnostico();
  renderMercado();
  const temTrilha = !!p.trilhaSalvaEm && S.analisado;
  exibirPainelTrilha(false);
  if (temTrilha) gerar(true);
  go(vistaDoEndereco() || 'inicio', true);
}

function init() {
  if (ERRO_CARGA) {
    mostrarErroDeCarga(ERRO_CARGA);
    return;
  }
  descartarProgressoPersistente();
  initTheme({ onChange: () => { if (document.getElementById('redeCompleta').open) drawGraph(); } });
  initMotion();
  initModals();
  initNavigation();

  registerViewHooks('diagnostico', { antes: renderDiagnostico });
  registerViewHooks('mercado', { antes: renderMercado });
  registerViewHooks('coordenacao', { antes: renderCoord });
  registerViewHooks('trilha', { depois: garantirTrilha });

  initCourses();
  initDiagnostic();
  initMarket();
  initGraph();
  initRecommendations();
  initCoordination();

  renderSobre();

  renderPicks();
  syncLocks();
  renderSheet();
  renderMercado();
  syncOpcoesTrilha();
  restaurarSessao();
  document.getElementById('main').setAttribute('aria-busy', 'false');
}

init();
