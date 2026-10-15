// Arquivos gerados no próprio navegador, sem servidor.

export function baixar(nome, conteudo, tipo) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([conteudo], { type: tipo }));
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1500);
}

const csvCel = (v) => {
  const s = String(v == null ? '' : v);
  return /[";\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

/** Separador ";" e BOM para o Excel abrir os acentos corretamente. */
export const paraCsv = (linhas) => `﻿${linhas.map((l) => l.map(csvCel).join(';')).join('\r\n')}`;

export const hojeArq = () => new Date().toISOString().slice(0, 10);
