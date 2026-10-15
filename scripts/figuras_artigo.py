"""Gera as figuras do artigo a partir dos artefatos (sem números digitados à mão).

Saída: docs/figuras/*.png (300 dpi). Uso: python scripts/figuras_artigo.py
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from edutrack.recommend.engine import Base  # noqa: E402

OUT = RAIZ / "docs" / "figuras"
OUT.mkdir(parents=True, exist_ok=True)
TINTA, AGUA2, AGUA3, AGUA4, LINHA = "#2B1B12", "#6B4529", "#A27849", "#CDAE82", "#A9B4AC"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": LINHA, "axes.labelcolor": TINTA,
                     "xtick.color": TINTA, "ytick.color": TINTA, "text.color": TINTA})


def caixa(ax, x, y, w, h, texto, cor="#F2F5F2", borda=TINTA, negrito=False, tam=9.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02", fc=cor, ec=borda, lw=1.2))
    ax.text(x + w / 2, y + h / 2, texto, ha="center", va="center", fontsize=tam, fontweight="bold" if negrito else "normal",
            color="white" if cor in (TINTA, AGUA2) else TINTA, wrap=True)


def seta(ax, a, b):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, lw=1.2, color=TINTA))


def arquitetura():
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    # camada de dados (offline)
    ax.text(0.01, 0.96, "Pipeline offline (pesquisador)", fontsize=10, fontweight="bold")
    caixa(ax, 0.01, 0.70, 0.17, 0.18, "Programa de Disciplina\n(PDF oficial)\n+ grade do histórico")
    caixa(ax, 0.01, 0.46, 0.17, 0.18, "Talent.com\n(robots.txt, 1,5 s)\nvagas de Manaus")
    caixa(ax, 0.23, 0.70, 0.16, 0.18, "parse_ppc.py\nextração e\ncontagem 32/39")
    caixa(ax, 0.23, 0.46, 0.16, 0.18, "scrape_talent.py\nfiltros, deduplicação\nremoção de dados pessoais")
    caixa(ax, 0.44, 0.58, 0.16, 0.18, "Normalização\nexata + aproximada\nlimiar 0,87\nontologia (76)", cor=AGUA4)
    caixa(ax, 0.65, 0.58, 0.15, 0.18, "Grafo heterogêneo\ndisciplina · habilidade\n· vaga", cor=AGUA3)
    caixa(ax, 0.84, 0.58, 0.15, 0.18, "GraphSAGE (NumPy)\n+ TF-IDF\navaliação 20 sementes", cor=AGUA2)
    for a, b in [((0.18, 0.79), (0.23, 0.79)), ((0.18, 0.55), (0.23, 0.55)), ((0.39, 0.79), (0.44, 0.70)),
                 ((0.39, 0.55), (0.44, 0.64)), ((0.60, 0.67), (0.65, 0.67)), ((0.80, 0.67), (0.84, 0.67))]:
        seta(ax, a, b)
    caixa(ax, 0.62, 0.30, 0.37, 0.13, "Artefatos versionados: grafo.npz, pesos, afinidades,\nmétricas, energia (artifacts/)", cor="#FFFFFF")
    seta(ax, (0.915, 0.58), (0.915, 0.43))
    ax.text(0.01, 0.30, "Aplicação (usuário)", fontsize=10, fontweight="bold")
    caixa(ax, 0.01, 0.04, 0.27, 0.20, "Página principal (HTML, CSS, JS)\n8 abas: estudante e coordenação\nsem login, nada gravado no servidor", cor="#FFFFFF")
    caixa(ax, 0.36, 0.04, 0.27, 0.20, "API FastAPI (somente leitura)\n/api/interface · /api/trilha\n/api/diagnostico · /api/normalizar", cor=TINTA)
    caixa(ax, 0.71, 0.04, 0.28, 0.20, "Motor de recomendação\ncobertura máxima gulosa\npré-requisitos (RN03)", cor="#F2F5F2")
    seta(ax, (0.28, 0.14), (0.36, 0.14))
    seta(ax, (0.63, 0.14), (0.71, 0.14))
    seta(ax, (0.80, 0.30), (0.80, 0.24))
    fig.savefig(OUT / "fig_arquitetura.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def esquema_grafo(val):
    n, e = val["tipos_de_no"], val["tipos_de_aresta"]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    caixa(ax, 0.03, 0.55, 0.24, 0.26, f"Disciplina\n{n['disciplina']['nos']} nós\n(domínio Acadêmico)", cor=TINTA, negrito=True, tam=10.5)
    caixa(ax, 0.38, 0.55, 0.24, 0.26, f"Habilidade\n{n['skill']['nos']} nós\n(ontologia)", cor=AGUA3, negrito=True, tam=10.5)
    caixa(ax, 0.73, 0.55, 0.24, 0.26, f"Vaga\n{n['vaga']['nos']} nós\n(domínio Mercado)", cor=AGUA4, negrito=True, tam=10.5)
    seta(ax, (0.27, 0.68), (0.38, 0.68))
    ax.text(0.325, 0.72, f"ensina\n({e['disciplina-ensina-skill']})", ha="center", fontsize=9)
    seta(ax, (0.73, 0.68), (0.62, 0.68))
    ax.text(0.675, 0.72, f"exige\n({e['vaga-exige-skill']})", ha="center", fontsize=9)
    ax.annotate("", xy=(0.10, 0.55), xytext=(0.20, 0.55), arrowprops=dict(arrowstyle="-|>", connectionstyle="arc3,rad=-1.2", color=TINTA, lw=1.2))
    ax.text(0.15, 0.30, f"pré-requisito ({e['disciplina-pre_requisito-disciplina']})", ha="center", fontsize=9)
    ax.annotate("", xy=(0.45, 0.55), xytext=(0.55, 0.55), arrowprops=dict(arrowstyle="-", connectionstyle="arc3,rad=-1.2", color=TINTA, lw=1.2))
    ax.text(0.50, 0.30, f"coocorrência nas vagas ({e['skill-coocorrencia-skill']},\nponderada, ≥ 2 vagas)", ha="center", fontsize=9)
    ax.text(0.5, 0.08, "O perfil do estudante não é um nó: é um filtro aplicado no momento da consulta.", ha="center", fontsize=9, style="italic")
    fig.savefig(OUT / "fig_grafo.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


ROTULOS = {"GraphSAGE + texto (híbrido)": "GNN híbrida", "GraphSAGE (GNN)": "GNN (GraphSAGE)",
           "GNN sem mensagens (L=0)": "GNN sem mensagens", "TF-IDF (cosseno)": "TF-IDF",
           "Coocorrência (heurística)": "Coocorrência", "Popularidade": "Popularidade"}


def resultados(aval):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, (cen, titulo) in zip(axes, [("texto_mascarado", "Vínculos latentes (texto mascarado)"),
                                        ("texto_completo", "Vínculos explícitos (texto completo)")]):
        ag = aval["agregado"][cen]
        modelos = list(ag)
        vals = [ag[m]["R@5"]["media"] for m in modelos]
        dps = [ag[m]["R@5"]["dp"] for m in modelos]
        y = range(len(modelos))
        ax.barh(y, vals, height=0.55, color=AGUA3, xerr=dps, error_kw=dict(ecolor=TINTA, lw=0.8, capsize=2))
        for yi, v in zip(y, vals):
            ax.text(v + 0.03, yi, f"{v:.3f}".replace(".", ","), va="center", fontsize=8.5)
        ax.set_yticks(list(y), [ROTULOS[m] for m in modelos])
        ax.invert_yaxis()
        ax.set_xlim(0, 1.15)
        ax.set_xlabel("Recall@5 (média ± dp, 20 sementes)")
        ax.set_title(titulo, fontsize=10)
        ax.grid(axis="x", color="#E3E8E4", lw=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_resultados.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def lacunas(diag, n=12):
    itens = diag["lacunas"][:n]
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    y = range(len(itens))
    vals = [100 * x["demanda"] for x in itens]
    ax.barh(y, vals, height=0.6, color=AGUA3)
    for yi, x in zip(y, itens):
        ax.text(100 * x["demanda"] + 0.6, yi, f"{x['vagas']} vagas", va="center", fontsize=8.5)
    ax.set_yticks(list(y), [x["nome"] for x in itens])
    ax.invert_yaxis()
    ax.set_xlabel(f"% das {diag['vagas_consideradas']} vagas de TI de Manaus que exigem a habilidade")
    ax.set_xlim(0, max(vals) * 1.25)
    ax.grid(axis="x", color="#E3E8E4", lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_lacunas.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    val = json.loads((RAIZ / "artifacts" / "graph" / "validacao.json").read_text(encoding="utf-8"))
    aval = json.loads((RAIZ / "artifacts" / "metrics" / "avaliacao.json").read_text(encoding="utf-8"))
    arquitetura()
    esquema_grafo(val)
    resultados(aval)
    lacunas(Base.carregar().diagnostico())
    print("figuras em", OUT)


if __name__ == "__main__":
    main()
