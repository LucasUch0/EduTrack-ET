"""Grafo de conhecimento heterogêneo (RF17–RF22).

Estrutura no mesmo formato conceitual do ``HeteroData`` do PyTorch Geometric
— nós e arestas indexados por tipo —, implementada em NumPy para dispensar o
PyTorch (decisão registrada em docs/MUDANCAS_v1.2.md):

    g.nos["disciplina"]["x"]                      matriz de atributos
    g.arestas[("disciplina", "ensina", "skill")]   índice 2 x E (+ pesos)

Tipos de nó, nos dois domínios do modelo (Acadêmico e Mercado):
    disciplina (Acadêmico) · skill (compartilhado) · vaga (Mercado)
Tipos de aresta (RF18):
    disciplina -ensina-> skill · vaga -exige-> skill ·
    disciplina -pre_requisito-> disciplina · skill -coocorrencia- skill

O perfil do estudante não é nó: é um filtro em tempo de consulta (seção 7.1 do
documento de requisitos).
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np

from edutrack.core.texto import titulo_pt
from edutrack.config import artefatos, caminho, carregar_config, processados
from edutrack.normalize.normalize_skills import Ontologia

TIPOS = ("disciplina", "skill", "vaga")
ENSINA = ("disciplina", "ensina", "skill")
EXIGE = ("vaga", "exige", "skill")
PREREQ = ("disciplina", "pre_requisito", "disciplina")
COOC = ("skill", "coocorrencia", "skill")
PERFIS = ("desenvolvimento", "dados_ia", "infraestrutura", "industria", "corporativo")

_STOPWORDS_PT = (
    "a o e é de da do das dos em no na nos nas um uma uns umas para por com sem sob sobre entre ao aos à às "
    "que se como mais menos ou seu sua seus suas ser ter são foi há etc já também muito muita muitos muitas "
    "este esta estes estas esse essa esses essas isso isto aquele aquela onde quando qual quais nosso nossa "
    "você vocês nós eles elas ele ela pelo pela pelos pelas até após the and of to in for with on at by from"
).split()


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c)).lower()


class HeteroGrafo:
    """Contêiner mínimo de grafo heterogêneo (nós e arestas por tipo)."""

    def __init__(self):
        self.nos: dict[str, dict] = {}
        self.arestas: dict[tuple[str, str, str], dict] = {}

    # ---- acesso ----------------------------------------------------------
    def num(self, tipo: str) -> int:
        return len(self.nos[tipo]["ids"])

    def idx(self, tipo: str) -> dict[str, int]:
        if "_idx" not in self.nos[tipo]:
            self.nos[tipo]["_idx"] = {k: i for i, k in enumerate(self.nos[tipo]["ids"])}
        return self.nos[tipo]["_idx"]

    def pares(self, rel: tuple) -> set[tuple[int, int]]:
        ei = self.arestas[rel]["index"]
        return set(zip(ei[0].tolist(), ei[1].tolist()))

    # ---- RF20: validação --------------------------------------------------
    def validar(self) -> dict:
        relatorio = {"tipos_de_no": {}, "tipos_de_aresta": {}, "problemas": []}
        grau = {t: np.zeros(self.num(t), dtype=int) for t in self.nos}
        for rel, a in self.arestas.items():
            src, _, dst = rel
            ei = a["index"]
            if ei.size == 0:
                relatorio["problemas"].append(f"tipo de aresta vazio: {rel}")
            ok = (ei[0] >= 0) & (ei[0] < self.num(src)) & (ei[1] >= 0) & (ei[1] < self.num(dst)) if ei.size else np.ones(0, bool)
            if not ok.all():
                relatorio["problemas"].append(f"índice fora do intervalo em {rel}: {int((~ok).sum())} aresta(s)")
            np.add.at(grau[src], ei[0][ok], 1)
            np.add.at(grau[dst], ei[1][ok], 1)
            relatorio["tipos_de_aresta"]["-".join(rel)] = int(ei.shape[1])
        for t in self.nos:
            isolados = [self.nos[t]["ids"][i] for i in np.where(grau[t] == 0)[0]]
            relatorio["tipos_de_no"][t] = {"nos": self.num(t), "atributos": int(self.nos[t]["x"].shape[1]),
                                           "isolados": len(isolados), "ids_isolados": isolados}
            if self.nos[t]["x"].shape[0] != self.num(t):
                relatorio["problemas"].append(f"matriz de atributos de {t} com linhas != nós")
            if not np.isfinite(self.nos[t]["x"]).all():
                relatorio["problemas"].append(f"atributos não finitos em {t}")
        relatorio["valido"] = not relatorio["problemas"]
        return relatorio

    # ---- RF21: exportação ---------------------------------------------------
    def salvar(self, pasta: Path) -> None:
        pasta.mkdir(parents=True, exist_ok=True)
        arrays = {}
        meta = {"nos": {}, "arestas": []}
        for t, n in self.nos.items():
            arrays[f"x__{t}"] = n["x"]
            meta["nos"][t] = {"ids": n["ids"], "nomes": n.get("nomes", n["ids"]), "atributos": n.get("atributos", [])}
        for rel, a in self.arestas.items():
            k = "__".join(rel)
            arrays[f"ei__{k}"] = a["index"]
            arrays[f"w__{k}"] = a.get("peso", np.ones(a["index"].shape[1]))
            meta["arestas"].append(list(rel))
        np.savez_compressed(pasta / "grafo.npz", **arrays)
        (pasta / "grafo_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def carregar(cls, pasta: Path) -> "HeteroGrafo":
        meta = json.loads((pasta / "grafo_meta.json").read_text(encoding="utf-8"))
        arr = np.load(pasta / "grafo.npz")
        g = cls()
        for t, m in meta["nos"].items():
            g.nos[t] = {"ids": m["ids"], "nomes": m["nomes"], "atributos": m["atributos"], "x": arr[f"x__{t}"]}
        for rel in meta["arestas"]:
            k = "__".join(rel)
            g.arestas[tuple(rel)] = {"index": arr[f"ei__{k}"], "peso": arr[f"w__{k}"]}
        return g

    # ---- RF22: subgrafo centrado -------------------------------------------
    def subgrafo(self, tipo: str, no_id: str, max_vizinhos: int = 40) -> dict:
        """Vizinhança de 1 salto de um nó, em todos os tipos de aresta."""
        i = self.idx(tipo)[no_id]
        nos = {(tipo, i)}
        arestas = []
        for rel, a in self.arestas.items():
            src, nome, dst = rel
            ei, w = a["index"], a.get("peso", np.ones(a["index"].shape[1]))
            for e in range(ei.shape[1]):
                u, v = int(ei[0, e]), int(ei[1, e])
                if (src == tipo and u == i) or (dst == tipo and v == i):
                    arestas.append((src, u, nome, dst, v, float(w[e])))
        arestas.sort(key=lambda r: -r[5])
        arestas = arestas[:max_vizinhos]
        for src, u, _, dst, v, _ in arestas:
            nos.add((src, u))
            nos.add((dst, v))
        return {
            "centro": {"tipo": tipo, "id": no_id},
            "nos": [{"tipo": t, "id": self.nos[t]["ids"][k], "nome": self.nos[t]["nomes"][k]} for t, k in sorted(nos)],
            "arestas": [{"origem": self.nos[s]["ids"][u], "tipo_origem": s, "relacao": n,
                         "destino": self.nos[d]["ids"][v], "tipo_destino": d, "peso": p}
                        for s, u, n, d, v, p in arestas],
        }


# ---------------------------------------------------------------------------
# Atributos textuais compartilhados (TF-IDF -> SVD) — também usados pela GNN
# ---------------------------------------------------------------------------
def documento_skill(h) -> str:
    return " ; ".join([h.nome] + list(h.aliases) + list(h.aliases_cs))


def vetorizador_tfidf():
    from sklearn.feature_extraction.text import TfidfVectorizer

    return TfidfVectorizer(preprocessor=sem_acento, stop_words=[sem_acento(w) for w in _STOPWORDS_PT],
                           ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"(?u)\b[\w#+.]*\w[\w#+]*\b")


def atributos_texto(textos: list[str], dim: int, semente: int) -> np.ndarray:
    """TF-IDF seguido de SVD truncada (LSA), padronizado por coluna."""
    from sklearn.decomposition import TruncatedSVD

    tf = vetorizador_tfidf().fit_transform(textos)
    k = min(dim, tf.shape[1] - 1, tf.shape[0] - 1)
    z = TruncatedSVD(n_components=k, random_state=semente).fit_transform(tf)
    z = (z - z.mean(0)) / (z.std(0) + 1e-8)
    if k < dim:
        z = np.hstack([z, np.zeros((z.shape[0], dim - k))])
    return z


# ---------------------------------------------------------------------------
# Construção a partir dos dados processados
# ---------------------------------------------------------------------------
def carregar_dados() -> dict:
    out = processados()
    return {
        "disciplinas": json.loads((out / "disciplinas.json").read_text(encoding="utf-8")),
        "disc_hab": json.loads((out / "disciplinas_habilidades.json").read_text(encoding="utf-8")),
        "vagas": json.loads((out / "vagas.json").read_text(encoding="utf-8")),
        "prereq": json.loads(caminho("prerequisitos").read_text(encoding="utf-8"))["arestas"],
        "ont": Ontologia(caminho("ontologia")),
    }


def construir(dados: dict | None = None, textos_disciplina: dict | None = None,
              arestas_ensina: list[tuple[str, str]] | None = None, semente: int = 42) -> HeteroGrafo:
    """Monta o grafo. ``textos_disciplina`` permite substituir o texto das
    ementas (cenário mascarado) e ``arestas_ensina`` restringir as arestas
    disciplina-skill visíveis (partição de treino)."""
    cfg = carregar_config()
    d = dados or carregar_dados()
    ont: Ontologia = d["ont"]
    g = HeteroGrafo()

    disc = d["disciplinas"]
    skills = list(ont.habilidades.values())
    vagas = d["vagas"]
    g.nos["disciplina"] = {"ids": [x["id"] for x in disc], "nomes": [titulo_pt(x["nome"]) for x in disc]}
    g.nos["skill"] = {"ids": [h.id for h in skills], "nomes": [h.nome for h in skills]}
    g.nos["vaga"] = {"ids": [v["id"] for v in vagas], "nomes": [v["titulo"] for v in vagas]}
    di, si, vi = g.idx("disciplina"), g.idx("skill"), g.idx("vaga")

    # ---- arestas ----
    if arestas_ensina is None:
        arestas_ensina = [(k, h["skill"]) for k, v in d["disc_hab"].items() for h in v["habilidades"]]
    ens = np.array([[di[a] for a, _ in arestas_ensina], [si[b] for _, b in arestas_ensina]], dtype=int).reshape(2, -1)
    g.arestas[ENSINA] = {"index": ens, "peso": np.ones(ens.shape[1])}

    ex = [(vi[v["id"]], si[s]) for v in vagas for s in v["habilidades"]]
    g.arestas[EXIGE] = {"index": np.array(ex, dtype=int).T.reshape(2, -1), "peso": np.ones(len(ex))}

    pr = [(di[p["disciplina"]], di[p["requer"]]) for p in d["prereq"] if p["disciplina"] in di and p["requer"] in di]
    g.arestas[PREREQ] = {"index": np.array(pr, dtype=int).T.reshape(2, -1), "peso": np.ones(len(pr))}

    cont = Counter()
    for v in vagas:
        for a, b in combinations(sorted(set(v["habilidades"])), 2):
            cont[(a, b)] += 1
    minimo = cfg["grafo"]["coocorrencia_minima"]
    co = [(si[a], si[b], n) for (a, b), n in cont.items() if n >= minimo]
    g.arestas[COOC] = {"index": np.array([[a for a, _, _ in co], [b for _, b, _ in co]], dtype=int).reshape(2, -1),
                       "peso": np.array([n for _, _, n in co], dtype=float)}

    # ---- atributos (RF19) ----
    dim = cfg["grafo"]["dim_texto_svd"]
    tdisc = [(textos_disciplina or {}).get(x["id"], d["disc_hab"][x["id"]]["texto"]) for x in disc]
    tskill = [documento_skill(h) for h in skills]
    tvaga = [v["texto"] for v in vagas]
    z = atributos_texto(tdisc + tskill + tvaga, dim, semente)
    zd, zs, zv = z[: len(disc)], z[len(disc): len(disc) + len(skills)], z[len(disc) + len(skills):]

    periodos = cfg["ppc"]["periodos_esperados"]
    ch = np.array([x["carga_horaria"] or np.nan for x in disc], dtype=float)
    ch = np.where(np.isnan(ch), np.nanmean(ch), ch) / float(cfg["grafo"]["escala_carga_horaria"])
    xd = np.hstack([
        np.eye(periodos)[[x["periodo"] - 1 for x in disc]],
        ch[:, None],
        np.array([[1.0 if x["fonte_ementa"] == "programa_oficial" else 0.0] for x in disc]),
        zd,
    ])
    cats = list(ont.categorias)
    demanda = Counter(s for v in vagas for s in set(v["habilidades"]))
    xs = np.hstack([
        np.eye(len(cats))[[cats.index(h.categoria) for h in skills]],
        np.array([[demanda[h.id] / max(len(vagas), 1)] for h in skills]),
        zs,
    ])
    xv = np.hstack([
        np.eye(len(PERFIS))[[PERFIS.index(v["perfil"]) for v in vagas]],
        np.array([[len(v["habilidades"]) / float(cfg["grafo"]["escala_habilidades_vaga"])] for v in vagas]),
        zv,
    ])
    g.nos["disciplina"]["x"], g.nos["skill"]["x"], g.nos["vaga"]["x"] = xd, xs, xv
    g.nos["disciplina"]["atributos"] = [f"periodo_{p+1}" for p in range(periodos)] + ["carga_horaria", "ementa_oficial"] + [f"lsa_{i}" for i in range(dim)]
    g.nos["skill"]["atributos"] = [f"cat_{c}" for c in cats] + ["demanda"] + [f"lsa_{i}" for i in range(dim)]
    g.nos["vaga"]["atributos"] = [f"perfil_{p}" for p in PERFIS] + ["n_habilidades"] + [f"lsa_{i}" for i in range(dim)]
    return g


def main() -> None:
    g = construir()
    rel = g.validar()
    pasta = artefatos() / "graph"
    g.salvar(pasta)
    (pasta / "validacao.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in rel.items()}, ensure_ascii=False, indent=1)[:3000])


if __name__ == "__main__":
    main()
