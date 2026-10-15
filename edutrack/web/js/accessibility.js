// Tema, redução de movimento e operação por teclado.

import { STORAGE } from './config.js';
import { toast } from './ui.js';

// Preferência de aparência não é dado do estudante: pode sobreviver à sessão.
const guardar = (chave, valor) => { try { localStorage.setItem(chave, valor); } catch { /* sem persistência */ } };
const ler = (chave) => { try { return localStorage.getItem(chave); } catch { return null; } };

let aoTrocarTema = () => {};

export function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  guardar(STORAGE.tema, t);
  document.querySelectorAll('.ic-sun').forEach((i) => { i.style.display = t === 'dark' ? 'none' : 'block'; });
  document.querySelectorAll('.ic-moon').forEach((i) => { i.style.display = t === 'dark' ? 'block' : 'none'; });
  aoTrocarTema(t);
}

export function initTheme({ onChange } = {}) {
  aoTrocarTema = onChange || (() => {});
  setTheme(ler(STORAGE.tema) || 'dark');
  document.querySelectorAll('.theme-btn').forEach((b) => b.addEventListener('click', () => {
    setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  }));
}

export function initMotion() {
  const botao = document.getElementById('a11yBtn');
  const aplicar = (reduzir) => {
    document.documentElement.style.setProperty('--dur', reduzir ? '.001ms' : '.2s');
    document.documentElement.toggleAttribute('data-motion-reduced', reduzir);
    botao.setAttribute('aria-pressed', String(reduzir));
    guardar(STORAGE.movimento, reduzir ? '1' : '0');
  };
  aplicar(ler(STORAGE.movimento) === '1');
  botao.addEventListener('click', () => {
    const reduzir = botao.getAttribute('aria-pressed') !== 'true';
    aplicar(reduzir);
    toast('info', 'Preferência salva', reduzir ? 'Animações reduzidas.' : 'Animações normais.', 2200);
  });
}

/** Elemento não nativo que responde a Enter e Espaço além do clique (RNF10). */
export function tornarAcionavel(el, acao) {
  el.tabIndex = 0;
  el.addEventListener('click', acao);
  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); acao(); }
  });
}
