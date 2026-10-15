// Diálogos: prendem o foco enquanto abertos e o devolvem a quem abriu.

import { S } from './state.js';

const FOCAVEIS = 'button,input,select,[tabindex]:not([tabindex="-1"])';

export function openOv(ov) {
  S.lastFocus = document.activeElement;
  ov.classList.add('open');  // .ov.open fica visível sem transição: elemento oculto não recebe foco
  const d = ov.querySelector('.dlg');
  const focaveis = () => [...d.querySelectorAll(FOCAVEIS)].filter((x) => !x.disabled && x.offsetParent !== null);
  const primeiro = focaveis()[0];
  if (primeiro) primeiro.focus();
  const trap = (e) => {
    if (e.key === 'Escape') { closeOv(ov); return; }
    if (e.key !== 'Tab') return;
    const lista = focaveis();
    if (!lista.length) return;
    const a = lista[0];
    const b = lista[lista.length - 1];
    if (!d.contains(document.activeElement)) { e.preventDefault(); (e.shiftKey ? b : a).focus(); }
    else if (e.shiftKey && document.activeElement === a) { e.preventDefault(); b.focus(); }
    else if (!e.shiftKey && document.activeElement === b) { e.preventDefault(); a.focus(); }
  };
  document.addEventListener('keydown', trap);
  ov._trap = trap;
}

export function closeOv(ov) {
  ov.classList.remove('open');
  if (ov._trap) document.removeEventListener('keydown', ov._trap);
  if (S.lastFocus) S.lastFocus.focus();
}

export function info(title, sub, html) {
  document.getElementById('infoT').textContent = title;
  document.getElementById('infoS').textContent = sub || '';
  document.getElementById('infoB').innerHTML = html;
  openOv(document.getElementById('ovInfo'));
}

export function confirmar(title, html, cb, label) {
  const ov = document.getElementById('ovConfirm');
  document.getElementById('cfT').textContent = title;
  document.getElementById('cfB').innerHTML = html;
  const antigo = document.getElementById('cfOk');
  const novo = antigo.cloneNode(true);
  novo.textContent = label || 'Confirmar';
  antigo.parentNode.replaceChild(novo, antigo);
  novo.addEventListener('click', () => { closeOv(ov); cb(); });
  openOv(ov);
}

export function initModals() {
  document.querySelectorAll('.ov').forEach((ov) => {
    ov.addEventListener('mousedown', (e) => { if (e.target === ov) closeOv(ov); });
    ov.querySelectorAll('[data-x]').forEach((b) => b.addEventListener('click', () => closeOv(ov)));
  });
}
