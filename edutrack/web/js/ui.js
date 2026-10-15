// Formatação e peças visuais reutilizadas por todas as telas.

export const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** Número com vírgula decimal. */
export const br = (n) => String(n).replace('.', ',');

/** "2026-09-02" → "02/09/2026" */
export const dataCurta = (iso) => {
  if (!iso) return '—';
  const p = String(iso).slice(0, 10).split('-');
  return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : String(iso);
};

/** 0,4 → "40%"; casas decimais opcionais, vírgula como separador. */
export const pct = (x, casas = 0) => `${br((100 * x).toFixed(casas))}%`;

/** Número com casas fixas e vírgula decimal. */
export const num = (x, casas = 2) => br(Number(x).toFixed(casas));

export const deb = (f, w) => {
  let t;
  return function (...args) { clearTimeout(t); t = setTimeout(() => f.apply(this, args), w); };
};

const icone = (conteudo) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${conteudo}</svg>`;

export const TI = {
  ok: icone('<circle cx="12" cy="12" r="9"/><polyline points="8.5 12.5 11 15 15.5 9.5"/>'),
  warn: icone('<path d="M12 2.5 22.5 21H1.5z" stroke-linejoin="round"/><line x1="12" y1="9.5" x2="12" y2="14"/><line x1="12" y1="17" x2="12" y2="17.1"/>'),
  bad: icone('<circle cx="12" cy="12" r="9"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'),
  info: icone('<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/><line x1="12" y1="7.5" x2="12" y2="7.6"/>')
};

export function vazio(tipo, titulo, texto, estilo = '') {
  return `<div class="empty"${estilo ? ` style="${estilo}"` : ''}><div class="ic">${TI[tipo] || TI.info}</div>`
    + `<h3>${esc(titulo)}</h3><p>${esc(texto)}</p></div>`;
}

export const kpi = (k) => `<div class="kpi"><div class="v">${k.v}</div><div class="l">${k.l}</div><div class="s">${k.s}</div></div>`;

const VISTO = '<svg class="i chk-i" viewBox="0 0 24 24" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';

/** Competência como selo: quem já tem ganha um visto, não só outra cor (RNF13). */
export function chipCompetencia(nome, tem) {
  return `<span class="chip-s${tem ? '' : ' gap'}">${tem ? VISTO : ''}${esc(nome)}`
    + `<span class="sr">${tem ? ' (você já tem)' : ' (lacuna)'}</span></span>`;
}

/** Grupo de pílulas de escolha única. */
export function grupoDePills(container, aoEscolher) {
  const pills = [...container.querySelectorAll('.pill')];
  pills.forEach((p) => p.addEventListener('click', () => {
    pills.forEach((x) => x.setAttribute('aria-pressed', 'false'));
    p.setAttribute('aria-pressed', 'true');
    aoEscolher(p);
  }));
}

/** Aviso temporário; `acao` ({ rotulo, fn }) acrescenta um botão, como "Desfazer". */
export function toast(type, title, msg, dur, acao) {
  const el = document.createElement('div');
  el.className = `tst ${type}`;
  el.setAttribute('role', type === 'bad' ? 'alert' : 'status');
  el.innerHTML = `<span class="ti">${TI[type] || TI.info}</span>`
    + `<div style="flex:1"><div class="tt">${esc(title)}</div>${msg ? `<div class="tm">${esc(msg)}</div>` : ''}`
    + `${acao ? `<button class="btn btn-line btn-sm tst-acao">${esc(acao.rotulo)}</button>` : ''}</div>`
    + '<button class="tx" aria-label="Fechar aviso"><svg class="i" viewBox="0 0 24 24" aria-hidden="true" style="width:14px;height:14px"><line x1="6" y1="6" x2="18" y2="18"/><line x1="6" y1="18" x2="18" y2="6"/></svg></button>';
  document.getElementById('toasts').appendChild(el);
  const rm = () => { el.classList.add('out'); setTimeout(() => el.remove(), 220); };
  el.querySelector('.tx').addEventListener('click', rm);
  if (acao) el.querySelector('.tst-acao').addEventListener('click', () => { acao.fn(); rm(); });
  const t = setTimeout(rm, dur || 4200);
  el.addEventListener('mouseenter', () => clearTimeout(t));
  el.addEventListener('focusin', () => clearTimeout(t));
}
