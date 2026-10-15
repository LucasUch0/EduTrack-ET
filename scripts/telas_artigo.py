"""Capturas das telas da aplicação para o artigo (Figuras 6 e 7), com a aplicação rodando.

Reproduz o exemplo do artigo: estudante que concluiu os três primeiros períodos, trilha de
cinco disciplinas para todas as vagas, modelo padrão. Usa o tema claro, melhor para impressão.

Uso:  python iniciar.py --sem-navegador   (em outro terminal)
      python scripts/telas_artigo.py [http://127.0.0.1:8000/]
Requer Playwright com o Chromium (pip install playwright && playwright install chromium).
Saída: docs/figuras/tela_estudante.png e docs/figuras/tela_coordenacao.png
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[1]
FIG = RAIZ / "docs" / "figuras"
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"


def recorte(pg, inicio, fim, margem=24, base=4):
    """Retângulo da página do topo de `inicio` à base de `fim`, com a largura da área de conteúdo."""
    pg.evaluate("window.scrollTo(0, 0)")
    a = pg.locator(inicio).first.bounding_box()
    b = pg.locator(fim).first.bounding_box()
    x0 = max(0, a["x"] - margem)
    return {"x": x0, "y": a["y"] - margem, "width": min(a["width"] + 2 * margem, pg.viewport_size["width"] - x0),
            "height": b["y"] + b["height"] - a["y"] + margem + base}


def ir(pg, vista):
    """Troca de aba pelo próprio botão da navegação."""
    # menu, etapas da trilha (1 · 2 · 3) ou logotipo, conforme a aba
    pg.evaluate("v => document.querySelector(`.navlink[data-go='${v}'], .stp[data-go='${v}'], .brand[data-go='${v}']`).click()", vista)
    pg.wait_for_selector(f"#v-{vista}.active")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page(viewport={"width": 1000, "height": 900}, device_scale_factor=2.4, locale="pt-BR",
                          color_scheme="light", reduced_motion="reduce")
        erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(URL, wait_until="networkidle")
        pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        pg.add_style_tag(content=".toasts{display:none!important}")
        pg.wait_for_selector("#pickHost input[type=checkbox]", state="attached")

        # Meu perfil: os três primeiros períodos, como no exemplo do artigo
        ir(pg, "perfil")
        pg.evaluate("""() => document.querySelectorAll('#pickHost .per-group').forEach((g, i) => {
            if (i < 3) g.querySelectorAll('input').forEach((c) => { if (!c.checked) c.click(); }); })""")
        pg.click("#btnAnalisar")
        pg.wait_for_selector("#v-diagnostico.active")

        # Minha trilha: todas as vagas, k = 5, modelo padrão
        ir(pg, "trilha")
        pg.wait_for_selector("#triRes", state="visible", timeout=20000)  # calculada ao abrir a aba (padrão: todas as vagas)
        pg.wait_for_timeout(600)
        pg.screenshot(path=str(FIG / "tela_estudante.png"), full_page=True,
                      clip=recorte(pg, "#v-trilha .view-head", "#rank .rk:nth-child(2)"))

        # Coordenação: todas as vagas
        ir(pg, "coordenacao")
        pg.wait_for_selector("#coGaps table")
        pg.wait_for_timeout(600)
        pg.screenshot(path=str(FIG / "tela_coordenacao.png"), full_page=True,
                      clip=recorte(pg, "#v-coordenacao .view-head", "#coGaps tbody tr:nth-child(5)"))
        nav.close()
    if erros:
        raise SystemExit("Erros na página: " + "; ".join(erros))
    print("Capturas salvas em", FIG)


if __name__ == "__main__":
    main()
