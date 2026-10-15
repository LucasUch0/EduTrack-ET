"""Diagrama de classes UML do EduTrack-GNN (Graphviz), fiel às classes do código.

Saída: docs/figuras/fig_classes.png (300 dpi) e docs/figuras/diagrama_classes.dot.
Requer o Graphviz instalado (comando `dot`). Uso: python scripts/diagrama_classes.py
"""
import shutil
import subprocess
from html import escape
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
OUT = RAIZ / "docs" / "figuras"

# nome -> (estereótipo, atributos, métodos)
CLASSES = {
    "Coletor": ("", ["- sessao: Session", "- robots: RobotFileParser", "- requisicoes: int"],
                ["+ obter(caminho): str", "+ coletar(max_paginas): dict"]),
    "Ontologia": ("", ["+ categorias: dict", "+ habilidades: dict[str, Habilidade]"],
                  ["+ ids(): list", "+ sinonimos(): dict"]),
    "Habilidade": ("dataclass", ["+ id: str", "+ nome: str", "+ categoria: str", "+ aliases: list"], []),
    "Normalizador": ("", ["- limiar: float = 0,87", "- tamanho_minimo_fuzzy: int"],
                     ["+ extrair(texto, modo): list[Ocorrencia]", "+ normalizar_termo(termo): tuple",
                      "+ mascarar(texto, evidencias): str"]),
    "Ocorrencia": ("dataclass", ["+ termo_original: str", "+ skill_id: str", "+ camada: str", "+ escore: float"], []),
    "HeteroGrafo": ("", ["+ nos: dict[tipo, atributos]", "+ arestas: dict[relação, índices]"],
                    ["+ validar(): dict", "+ salvar(pasta)", "+ carregar(pasta): HeteroGrafo",
                     "+ subgrafo(tipo, id): dict"]),
    "SAGEHetero": ("", ["- params: dict[str, ndarray]", "- hp: Hiper"],
                   ["+ forward(X, M): dict", "+ backward(G, cache): dict", "+ embeddings(X, M): dict"]),
    "Hiper": ("dataclass", ["+ camadas: int = 2", "+ dim_oculta: int = 32", "+ dropout: float",
                            "+ decodificador_hibrido: bool"], []),
    "Adam": ("", ["- lr: float", "- wd: float"], ["+ passo(params, grads)"]),
    "ResultadoTreino": ("dataclass", ["+ modelo: SAGEHetero", "+ melhor_epoca: int", "+ historico: list"], []),
    "Base": ("motor de recomendação", ["+ disciplinas: list", "+ vagas: list", "+ afinidade: dict[modelo, matriz]"],
             ["+ trilha(cursadas, perfil, k, modelo): dict", "+ diagnostico(perfil): dict",
              "+ apoio_estrutural(habilidade): dict", "+ afinidade_disciplinas(habilidades): dict"]),
    "API": ("FastAPI", [], ["+ GET /api/interface", "+ POST /api/trilha", "+ GET /api/afinidade",
                           "+ GET /api/diagnostico[.csv]", "+ GET /api/normalizar",
                           "+ GET /api/normalizacao/auditoria", "+ GET /api/grafo/subgrafo"]),
    "TrilhaEntrada": ("Pydantic", ["+ cursadas: list[str]", "+ perfil: str", "+ k: int = 5", "+ modelo: str"], []),
    "RastreadorEnergia": ("", ["- etapa: str", "- p_nucleo: float"], ["+ __enter__()", "+ __exit__()"]),
    "Medicao": ("dataclass", ["+ duracao_s: float", "+ energia_kwh: float", "+ co2_g: float"], []),
}

# (origem, destino, tipo, rótulo); tipo: assoc | comp | dep
RELACOES = [
    ("Ontologia", "Habilidade", "comp", "1..*"),
    ("Normalizador", "Ontologia", "assoc", "usa"),
    ("Normalizador", "Ocorrencia", "dep", "produz"),
    ("Coletor", "Normalizador", "dep", "vagas"),
    ("HeteroGrafo", "Normalizador", "dep", "arestas ensina/exige"),
    ("SAGEHetero", "HeteroGrafo", "dep", "treina sobre"),
    ("SAGEHetero", "Hiper", "assoc", ""),
    ("Adam", "SAGEHetero", "dep", "otimiza"),
    ("ResultadoTreino", "SAGEHetero", "assoc", ""),
    ("Base", "SAGEHetero", "dep", "afinidades"),
    ("Base", "Ontologia", "assoc", ""),
    ("API", "Base", "assoc", "consulta"),
    ("API", "HeteroGrafo", "assoc", "subgrafo"),
    ("API", "TrilhaEntrada", "dep", "recebe"),
    ("API", "Normalizador", "assoc", "teste de termo"),
    ("RastreadorEnergia", "Medicao", "dep", "registra"),
]


def rotulo(nome, estereotipo, atributos, metodos):
    linhas = ['<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" COLOR="#2B1B12">']
    cab = (f'<FONT POINT-SIZE="9">«{escape(estereotipo)}»</FONT><BR/>' if estereotipo else "") + f"<B>{escape(nome)}</B>"
    linhas.append(f'<TR><TD BGCOLOR="#E9DCC8" ALIGN="CENTER">{cab}</TD></TR>')
    for grupo in (atributos, metodos):
        if grupo or grupo is atributos:
            corpo = '<BR ALIGN="LEFT"/>'.join(escape(x) for x in grupo) + ('<BR ALIGN="LEFT"/>' if grupo else " ")
            linhas.append(f'<TR><TD ALIGN="LEFT" BALIGN="LEFT" SIDES="T">{corpo}</TD></TR>')
    linhas.append("</TABLE>>")
    return "".join(linhas)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    estilos = {"assoc": 'arrowhead="vee"', "comp": 'arrowtail="diamond" dir="back" arrowhead="none"',
               "dep": 'style="dashed" arrowhead="vee"'}
    dot = ['digraph classes {', 'graph [rankdir=TB, splines=true, nodesep=0.35, ranksep=0.45, fontname="Helvetica"];',
           'node [shape=plain, fontname="Helvetica", fontsize=10];',
           'edge [fontname="Helvetica", fontsize=8, color="#2B1B12", fontcolor="#5A4E46"];']
    for nome, (est, at, me) in CLASSES.items():
        dot.append(f'"{nome}" [label={rotulo(nome, est, at, me)}];')
    for a, b, t, r in RELACOES:
        dot.append(f'"{a}" -> "{b}" [{estilos[t]}, label="{r}"];')
    dot += ['{rank=same; "Coletor"; "Ontologia"; "RastreadorEnergia";}',
            '{rank=same; "Base"; "TrilhaEntrada";}', "}"]
    fonte = OUT / "diagrama_classes.dot"
    fonte.write_text("\n".join(dot), encoding="utf-8")
    if not shutil.which("dot"):
        raise SystemExit("Graphviz (dot) não encontrado; o arquivo .dot foi gerado em " + str(fonte))
    subprocess.run(["dot", "-Tpng", "-Gdpi=300", str(fonte), "-o", str(OUT / "fig_classes.png")], check=True)
    print("diagrama em", OUT / "fig_classes.png")


if __name__ == "__main__":
    main()
