"""Auditoria da interface no navegador: acessibilidade (WCAG 2.1 AA) e requisitos da página.

Verifica, em cada uma das oito abas e nos dois temas:
  * nome acessível de todo controle, calculado pela árvore de acessibilidade do próprio Chromium (4.1.2)
  * rótulo visível contido no nome acessível (2.5.3)
  * contraste de todo texto visível, com as cores efetivas (1.4.3, RNF12)
  * idioma, título, ids duplicados, imagens sem alternativa, hierarquia de títulos (3.1.1, 2.4.2, 4.1.1, 1.1.1, 1.3.1)
e, uma vez:
  * percurso completo só com teclado, foco visível e ordem de foco (2.1.1, 2.4.3, 2.4.7, RNF10)
  * diálogo: foco entra, fica preso, Esc fecha e devolve o foco (2.1.2)
  * reflow em 320 px e zoom de 200% (1.4.10, 1.4.4), espaçamento de texto (1.4.12)
  * movimento reduzido, forma além da cor no grafo, tabela equivalente ao grafo (RNF11, RNF13)
  * nada guardado fora da aba, nenhuma requisição a terceiros, sem cookies (RF42, RN07)

Uso:  python iniciar.py --sem-navegador   (em outro terminal)
      python scripts/auditoria_interface.py [http://127.0.0.1:8000/] [saida.json]
Requer Playwright com o Chromium. Não faz parte das dependências da aplicação (RNF05).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"
SAIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("auditoria_interface.json")
VISTAS = ["inicio", "perfil", "diagnostico", "mercado", "trilha", "coordenacao", "sobre"]
PAPEIS_INTERATIVOS = {"button", "link", "checkbox", "radio", "textbox", "combobox", "listbox", "menuitem", "tab",
                      "switch", "searchbox", "spinbutton", "slider", "option"}

CONTRASTE_JS = r"""
() => {
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const mix = (top, bot) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + bot[i] * (1 - a)).concat([1]); };
  const fundo = (el) => { const pilha = []; let incerto = false;
    for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') incerto = true;
      const c = parse(cs.backgroundColor); if (c && c[3] > 0) { pilha.push(c); if (c[3] >= 1) break; } }
    let cor = [255, 255, 255, 1]; if (pilha.length && pilha[pilha.length - 1][3] >= 1) cor = pilha.pop();
    while (pilha.length) cor = mix(pilha.pop(), cor); return { cor, incerto }; };
  const desativado = (el) => !!el.closest('[disabled],[aria-disabled="true"]');
  const res = []; const vistos = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode; if (!n.textContent.trim()) continue;
    const el = n.parentElement; if (!el || vistos.has(el)) continue; vistos.add(el);
    if (el.closest('svg') && !el.closest('text')) continue;
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === 'hidden' || el.closest('[hidden],[aria-hidden="true"]') && !el.closest('svg')) continue;
    if (el.offsetParent === null && cs.position !== 'fixed') continue;
    if (el.closest('.sr, .skip')) continue;
    let op = 1; for (let e = el; e; e = e.parentElement) op *= Number(getComputedStyle(e).opacity);
    const fg0 = parse(el.tagName === 'text' || el.closest('svg') ? cs.fill : cs.color); if (!fg0) continue;
    const { cor: bg, incerto } = fundo(el);
    const fg = mix([fg0[0], fg0[1], fg0[2], fg0[3] * op], bg);
    const L1 = lum(fg), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const px = parseFloat(cs.fontSize); const bold = Number(cs.fontWeight) >= 700;
    const grande = px >= 24 || (bold && px >= 18.66);
    const minimo = grande ? 3 : 4.5;
    if (ratio < minimo) res.push({ texto: n.textContent.trim().slice(0, 60), ratio: Math.round(ratio * 100) / 100, minimo,
      desativado: desativado(el), incerto, seletor: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '') });
  }
  return res;
}
"""

ESTRUTURA_JS = r"""
() => {
  const ids = {}; document.querySelectorAll('[id]').forEach((e) => { ids[e.id] = (ids[e.id] || 0) + 1; });
  const ativa = document.querySelector('.view.active') || document.body;
  const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter((h) => h.offsetParent !== null).map((h) => Number(h.tagName[1]));
  const saltos = hs.filter((h, i) => i > 0 && h > hs[i - 1] + 1).length;
  return {
    lang: document.documentElement.lang, titulo: document.title,
    ids_duplicados: Object.entries(ids).filter(([, n]) => n > 1).map(([k]) => k),
    img_sem_alt: [...document.querySelectorAll('img:not([alt])')].length,
    tabindex_positivo: [...document.querySelectorAll('[tabindex]')].filter((e) => Number(e.getAttribute('tabindex')) > 0).length,
    h1_visiveis: hs.filter((h) => h === 1).length, saltos_de_titulo: saltos,
    focaveis_ocultos: [...document.querySelectorAll('[aria-hidden="true"] a[href], [aria-hidden="true"] button, [aria-hidden="true"] input')].filter((e) => e.offsetParent !== null).length,
  };
}
"""

FOCO_JS = r"""
() => { const e = document.activeElement; if (!e || e === document.body) return null;
  const cs = getComputedStyle(e); const r = e.getBoundingClientRect();
  const anel = (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== 'none');
  return { tag: e.tagName.toLowerCase(), id: e.id, texto: (e.getAttribute('aria-label') || e.textContent || e.value || '').trim().replace(/\s+/g, ' ').slice(0, 50),
           visivel: r.width > 0 && r.height > 0, foco_visivel: !!anel, dialogo: !!e.closest('[role="dialog"],dialog,.ov') };
}
"""


def nomes_faltando(cdp) -> list[dict]:
    arvore = cdp.send("Accessibility.getFullAXTree")["nodes"]
    falta, rotulo = [], []
    for n in arvore:
        if n.get("ignored"):
            continue
        papel = (n.get("role") or {}).get("value")
        if papel not in PAPEIS_INTERATIVOS:
            continue
        nome = ((n.get("name") or {}).get("value") or "").strip()
        if not nome:
            falta.append({"papel": papel, "no": n.get("backendDOMNodeId")})
    return falta


def rotulo_no_nome(pg) -> list[dict]:
    """2.5.3: controles com aria-label cujo texto visível não aparece no nome acessível."""
    return pg.evaluate(r"""() => {
      const norm = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
      return [...document.querySelectorAll('button[aria-label], a[aria-label]')].filter((b) => b.offsetParent !== null).map((b) => {
        const visivel = b.innerText || '';  // texto como aparece na tela (quebras de linha viram espaço)
        return { nome: b.getAttribute('aria-label'), visivel: visivel.replace(/\s+/g, ' ').trim() };
      }).filter((x) => /\p{L}/u.test(x.visivel) && !norm(x.nome).includes(norm(x.visivel).split(' ').slice(0, 2).join(' ')));
    }""")


def ir(pg, vista):
    # menu, etapas da trilha (1 · 2 · 3) ou logotipo, conforme a aba
    pg.evaluate("v => document.querySelector(`.navlink[data-go='${v}'], .stp[data-go='${v}'], .brand[data-go='${v}']`).click()", vista)
    pg.wait_for_selector(f"#v-{vista}.active")
    pg.wait_for_timeout(350)


def preparar(pg):
    """Perfil com os três primeiros períodos, para liberar as abas que dependem dele."""
    pg.goto(URL, wait_until="networkidle")
    pg.wait_for_selector("#pickHost input[type=checkbox]", state="attached")
    ir(pg, "perfil")
    pg.evaluate("""() => document.querySelectorAll('#pickHost .per-group').forEach((g, i) => {
        if (i < 3) g.querySelectorAll('input').forEach((c) => { if (!c.checked) c.click(); }); })""")
    pg.click("#btnAnalisar")
    pg.wait_for_selector("#v-diagnostico.active")


def tab_ate(pg, alvo_js: str, maximo: int = 400) -> int:
    for i in range(maximo):
        pg.keyboard.press("Tab")
        if pg.evaluate(f"() => {{ const e = document.activeElement; return !!e && ({alvo_js}); }}"):
            return i + 1
    raise AssertionError(f"teclado não alcançou: {alvo_js}")


def main():
    rel = {"por_vista": {}, "teclado": {}, "dialogo": {}, "reflow": {}, "espacamento": {}, "zoom200": {}, "graficos": {},
           "privacidade": {}, "movimento": {}}
    externos, erros = set(), []
    with sync_playwright() as p:
        nav = p.chromium.launch()

        # ---------- 1. regras automáticas por aba e tema ----------
        ctx = nav.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.on("request", lambda r: externos.add(r.url) if urlparse(r.url).hostname not in ("127.0.0.1", "localhost", None) and not r.url.startswith(("data:", "blob:")) else None)
        cdp = ctx.new_cdp_session(pg)
        cdp.send("Accessibility.enable")
        preparar(pg)
        pg.add_style_tag(content=".toasts{display:none!important}")
        for tema in ("dark", "light"):
            pg.evaluate(f"document.documentElement.setAttribute('data-theme', '{tema}')")
            for v in VISTAS:
                ir(pg, v)
                if v == "trilha":  # a trilha é calculada ao abrir a aba
                    pg.wait_for_selector("#triRes", state="visible", timeout=20000)
                    pg.wait_for_timeout(300)
                rel["por_vista"][f"{tema}/{v}"] = {
                    "sem_nome": nomes_faltando(cdp), "rotulo_fora_do_nome": rotulo_no_nome(pg),
                    "contraste": pg.evaluate(CONTRASTE_JS), "estrutura": pg.evaluate(ESTRUTURA_JS)}
            # diálogos abertos também passam pelas regras
            ir(pg, "coordenacao")  # detalhe de uma competência, aberto pela tabela do diagnóstico do curso
            pg.wait_for_selector("#coGaps tr[data-sk]")
            pg.click("#coGaps tr[data-sk]")
            pg.wait_for_timeout(300)
            rel["por_vista"][f"{tema}/dialogo_competencia"] = {"sem_nome": nomes_faltando(cdp), "contraste": pg.evaluate(CONTRASTE_JS),
                                                         "rotulo_fora_do_nome": rotulo_no_nome(pg)}
            pg.keyboard.press("Escape")

        # ---------- 2. só teclado: do primeiro acesso à trilha (RNF10, RNF13a) ----------
        kb = nav.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
        k = kb.new_page()
        k.goto(URL, wait_until="networkidle")
        k.wait_for_selector("#pickHost input[type=checkbox]", state="attached")
        k.keyboard.press("Tab")
        primeiro = k.evaluate(FOCO_JS)
        k.keyboard.press("Enter")  # link "Pular para o conteúdo"
        pulou = k.evaluate("() => location.hash === '#main' || document.activeElement.id === 'main' || !!document.activeElement.closest('main')")
        ordem, sem_anel = [], []
        k.evaluate("window.scrollTo(0,0); document.activeElement.blur()")
        for _ in range(60):  # ordem de foco na página inicial
            k.keyboard.press("Tab")
            f = k.evaluate(FOCO_JS)
            if not f:
                continue
            ordem.append(f["texto"] or f["tag"])
            if not f["foco_visivel"] or not f["visivel"]:
                sem_anel.append(f)
        passos = {}
        passos["montar_perfil"] = tab_ate(k, "e.classList.contains('cta')")
        k.keyboard.press("Enter")
        k.wait_for_selector("#v-perfil.active")
        passos["primeira_disciplina"] = tab_ate(k, "e.matches('#pickHost input[type=checkbox]')")
        marcadas = 0
        for _ in range(9):  # marca com Espaço as disciplinas do 1º e 2º períodos
            if k.evaluate("document.activeElement.matches('#pickHost input[type=checkbox]')"):
                k.keyboard.press("Space")
                marcadas += 1
            k.keyboard.press("Tab")
        passos["analisar"] = tab_ate(k, "e.id === 'btnAnalisar'")
        k.keyboard.press("Enter")
        k.wait_for_selector("#v-diagnostico.active")
        k.evaluate("window.scrollTo(0,0); document.activeElement.blur()")
        passos["aba_trilha"] = tab_ate(k, "e.matches('[data-go=\"trilha\"]')")
        k.keyboard.press("Enter")
        k.wait_for_selector("#v-trilha.active")
        k.wait_for_selector("#triRes", state="visible", timeout=20000)  # calculada ao abrir a aba, sem botão
        rel["teclado"] = {"primeiro_foco": primeiro, "pular_para_conteudo": pulou, "ordem_inicio": ordem[:40],
                          "focos_sem_indicador": sem_anel, "passos_tab": passos, "disciplinas_marcadas_com_espaco": marcadas,
                          "trilha_gerada_so_com_teclado": k.is_visible("#triRes"),
                          "itens_na_trilha": k.locator("#rank .rk").count()}

        # ---------- 3. diálogo: foco preso e devolvido (2.1.2) ----------
        k.evaluate("document.querySelector(\".navlink[data-go='coordenacao']\").focus()")
        k.keyboard.press("Enter")
        k.wait_for_selector("#coGaps tr[data-sk]")
        k.evaluate("document.activeElement.blur(); window.scrollTo(0,0)")
        tab_ate(k, "e.matches('#coGaps tr[data-sk]')")
        k.keyboard.press("Enter")
        k.wait_for_timeout(300)
        dentro = []
        for _ in range(12):
            dentro.append(k.evaluate("() => !!document.activeElement.closest('.ov.open, [role=dialog]')"))
            k.keyboard.press("Tab")
        k.keyboard.press("Escape")
        k.wait_for_timeout(300)
        volta = k.evaluate("() => document.activeElement.id || document.activeElement.dataset.sk || document.activeElement.tagName")
        rel["dialogo"] = {"foco_sempre_dentro": all(dentro), "esc_fecha": not k.is_visible(".ov.open"), "foco_volta_para": volta}

        # ---------- 4. privacidade no navegador (RF42, RN07) ----------
        armazenado = k.evaluate("() => ({session: Object.keys(sessionStorage), local: Object.keys(localStorage), cookies: document.cookie})")
        nova = nav.new_context(viewport={"width": 1366, "height": 900})
        n2 = nova.new_page()
        n2.goto(URL, wait_until="networkidle")
        n2.wait_for_selector("#pickHost input[type=checkbox]", state="attached")
        rel["privacidade"] = {"na_aba": armazenado,
                              "nova_sessao_marcadas": n2.evaluate("document.querySelectorAll('#pickHost input:checked').length"),
                              "nova_sessao_session_storage": n2.evaluate("Object.keys(sessionStorage)")}
        nova.close()

        # ---------- 5. gráficos: forma além da cor e tabela equivalente (RNF11, RNF13) ----------
        ir(pg, "sobre")
        pg.evaluate("document.getElementById('redeCompleta').open = true")  # rede completa recolhida em Sobre
        pg.wait_for_selector("#canvas svg")
        rel["graficos"] = pg.evaluate("""() => {
          const svg = document.querySelector('#canvas svg');
          return { circulos: svg.querySelectorAll('.gn circle').length, losangos: svg.querySelectorAll('.gn polygon').length,
                   arestas: svg.querySelectorAll('.ge').length, tracejadas: [...svg.querySelectorAll('.ge.pd')].length,
                   tracejado_css: svg.querySelector('.ge.pd') ? getComputedStyle(svg.querySelector('.ge.pd')).strokeDasharray : null,
                   nos_com_nome: [...svg.querySelectorAll('.gn')].every((g) => g.getAttribute('aria-label')),
                   nos_focaveis: [...svg.querySelectorAll('.gn')].every((g) => g.getAttribute('tabindex') === '0') };
        }""")
        pg.click("#tableBtn")
        pg.wait_for_timeout(300)
        rel["graficos"]["linhas_tabela"] = pg.locator("#graphTable tbody tr").count()
        rel["graficos"]["tabela_tem_cabecalho"] = pg.locator("#graphTable th[scope=col]").count()
        pg.click("#tableBtn")
        ir(pg, "trilha")  # grafo pessoal da trilha e sua tabela equivalente
        pg.wait_for_selector("#tgCanvas svg")
        rel["graficos"]["trilha"] = pg.evaluate("""() => {
          const svg = document.querySelector('#tgCanvas svg');
          return { disciplinas: svg.querySelectorAll('.tg-d').length, competencias: svg.querySelectorAll('.tg-c polygon').length,
                   arestas: svg.querySelectorAll('.tg-e').length,
                   nos_com_nome: [...svg.querySelectorAll('.tg-n')].every((g) => g.getAttribute('aria-label')),
                   nos_focaveis: [...svg.querySelectorAll('.tg-n')].every((g) => g.getAttribute('tabindex') === '0') };
        }""")
        pg.click("#tgTabela")
        rel["graficos"]["trilha"]["linhas_tabela"] = pg.locator("#tgTab tbody tr").count()
        pg.click("#tgTabela")
        ir(pg, "diagnostico")
        rel["graficos"]["prioridade_em_texto"] = pg.evaluate(
            "() => [...document.querySelectorAll('#gapHost .gap-card')].every((c) => /Prioridade (Alta|Média|Baixa)/.test(c.textContent))")

        # ---------- 6. reflow 320 px, zoom 200% e espaçamento de texto ----------
        for nome, largura in (("reflow", 320), ("zoom200", 683)):
            c2 = nav.new_context(viewport={"width": largura, "height": 800}, locale="pt-BR")
            q = c2.new_page()
            preparar(q)
            for v in VISTAS:
                ir(q, v)
                if v == "trilha":
                    q.wait_for_selector("#triRes", state="visible", timeout=20000)
                rel[nome][v] = q.evaluate("document.documentElement.scrollWidth")
            c2.close()
        q = ctx.new_page()
        preparar(q)
        q.add_style_tag(content="* { line-height: 1.5 !important; letter-spacing: .12em !important; word-spacing: .16em !important; }"
                                " p { margin-bottom: 2em !important; }")
        for v in VISTAS:
            ir(q, v)
            rel["espacamento"][v] = q.evaluate("""() => [...document.querySelectorAll('.view.active *')].filter((e) => {
                const cs = getComputedStyle(e); if (!/(hidden|clip)/.test(cs.overflow + cs.overflowX + cs.overflowY)) return false;
                if (!e.textContent.trim() || e.closest('svg') || e.matches('.sr, .skip')) return false;
                return e.scrollHeight > e.clientHeight + 2 || e.scrollWidth > e.clientWidth + 2; })
              .map((e) => e.tagName.toLowerCase() + '.' + String(e.className).trim().split(/\\s+/).join('.')).slice(0, 8)""")

        # ---------- 7. movimento reduzido ----------
        mr = nav.new_context(reduced_motion="reduce")
        m = mr.new_page()
        m.goto(URL, wait_until="networkidle")
        rel["movimento"] = {"duracao_transicao_com_reduce": m.evaluate("getComputedStyle(document.querySelector('.navlink')).transitionDuration")}
        mr.close()
        nav.close()

    rel["externos"] = sorted(externos)
    rel["erros_js"] = erros
    SAIDA.write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- resumo ----------
    def soma(chave, filtro=lambda x: True):
        return sum(len([x for x in r.get(chave, []) if filtro(x)]) for r in rel["por_vista"].values())
    print("sem nome acessível:", soma("sem_nome"))
    print("rótulo visível fora do nome:", soma("rotulo_fora_do_nome"), [x for r in rel["por_vista"].values() for x in r.get("rotulo_fora_do_nome", [])][:3])
    print("contraste insuficiente (ativos):", soma("contraste", lambda x: not x["desativado"]),
          "| em controles desativados (isentos):", soma("contraste", lambda x: x["desativado"]))
    est = [r["estrutura"] for r in rel["por_vista"].values() if "estrutura" in r]
    print("lang:", est[0]["lang"], "| ids duplicados:", sorted({i for e in est for i in e["ids_duplicados"]}),
          "| tabindex>0:", max(e["tabindex_positivo"] for e in est), "| saltos de título:", max(e["saltos_de_titulo"] for e in est))
    print("teclado:", json.dumps({k: v for k, v in rel["teclado"].items() if k != "ordem_inicio"}, ensure_ascii=False))
    print("diálogo:", rel["dialogo"])
    print("privacidade:", rel["privacidade"])
    print("gráficos:", rel["graficos"])
    print("reflow 320:", rel["reflow"], "| zoom 200%:", rel["zoom200"])
    print("espaçamento (cortes):", {k: v for k, v in rel["espacamento"].items() if v})
    print("movimento:", rel["movimento"], "| externos:", rel["externos"], "| erros JS:", erros)


if __name__ == "__main__":
    main()
