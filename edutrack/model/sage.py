"""GraphSAGE heterogêneo para predição de enlaces, em NumPy (RF23–RF26, RF40).

Camada l, para cada tipo de nó t (agregador de média, Hamilton, 2020):

    A_t = H_t W_self[t] + soma_r ( M_r H_src(r) ) W_r + b_t      (r com destino t)
    H'_t = ReLU(A_t)    (na última camada não há ReLU)

em que M_r é a matriz de adjacência da relação r normalizada por linha (média
dos vizinhos; ponderada na coocorrência). Antes da primeira camada, uma
projeção linear por tipo leva os atributos de cada tipo à mesma dimensão.
O escore de um par (disciplina d, habilidade s) é o produto interno z_d . z_s
e a probabilidade de enlace é sigmoid(z_d . z_s).

Treino: entropia cruzada binária entre arestas positivas e negativas
amostradas (3 negativas por positiva), otimizador Adam com decaimento de peso,
dropout e parada antecipada pela AUC de validação. A cada época as arestas de
treino são divididas em arestas de mensagem (70%) e de supervisão (30%), como
o ``disjoint_train_ratio`` do RandomLinkSplit — o modelo nunca vê na
agregação a aresta que está tentando prever. A tarefa auxiliar de reconstruir
as arestas vaga-exige-skill (peso lambda) ensina às habilidades a estrutura do
mercado. Os gradientes são calculados analiticamente e conferidos por
diferenças finitas em tests/test_sage.py.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

import numpy as np

from edutrack.graph.hetero import COOC, ENSINA, EXIGE, PREREQ, HeteroGrafo

# relações de mensagem: (tipo de origem, nome, tipo de destino)
RELACOES = (
    ("skill", "ensinada_por", "disciplina"),
    ("disciplina", "ensina", "skill"),
    ("skill", "exigida_por", "vaga"),
    ("vaga", "exige", "skill"),
    ("disciplina", "pre_requisito", "disciplina"),
    ("skill", "coocorrencia", "skill"),
)
TIPOS = ("disciplina", "skill", "vaga")


def matriz_media(n_dst: int, n_src: int, dst: np.ndarray, src: np.ndarray, peso: np.ndarray | None = None) -> np.ndarray:
    m = np.zeros((n_dst, n_src))
    np.add.at(m, (dst, src), 1.0 if peso is None else peso)
    grau = m.sum(1, keepdims=True)
    grau[grau == 0] = 1.0
    return m / grau


def matrizes_mensagem(g: HeteroGrafo, ensina: np.ndarray, exige: np.ndarray) -> dict:
    """``ensina`` e ``exige`` são arrays E x 2 (origem, destino) com as arestas
    visíveis para a agregação; pré-requisito e coocorrência vêm do grafo."""
    nd, ns, nv = g.num("disciplina"), g.num("skill"), g.num("vaga")
    pr = g.arestas[PREREQ]["index"]
    co, w = g.arestas[COOC]["index"], g.arestas[COOC]["peso"]
    return {
        RELACOES[0]: matriz_media(nd, ns, ensina[:, 0], ensina[:, 1]),
        RELACOES[1]: matriz_media(ns, nd, ensina[:, 1], ensina[:, 0]),
        RELACOES[2]: matriz_media(nv, ns, exige[:, 0], exige[:, 1]),
        RELACOES[3]: matriz_media(ns, nv, exige[:, 1], exige[:, 0]),
        RELACOES[4]: matriz_media(nd, nd, np.r_[pr[0], pr[1]], np.r_[pr[1], pr[0]]),
        RELACOES[5]: matriz_media(ns, ns, np.r_[co[0], co[1]], np.r_[co[1], co[0]], np.r_[w, w]),
    }


def sigmoid(x):
    return 0.5 * (1.0 + np.tanh(0.5 * x))


@dataclass
class Hiper:
    camadas: int = 2
    dim_oculta: int = 32
    dim_saida: int = 32
    dropout: float = 0.2
    taxa_aprendizado: float = 0.01
    decaimento_peso: float = 5e-4
    epocas: int = 300
    paciencia: int = 40
    negativos_por_positivo: int = 3
    fracao_supervisao: float = 0.3
    peso_auxiliar_exige: float = 0.5
    dim_texto: int = 16
    texto_compartilhado: bool = True
    residual: bool = True
    decodificador_hibrido: bool = False
    beta_inicial: float = 1.0

    @classmethod
    def de_config(cls, cfg: dict) -> "Hiper":
        m = cfg["modelo"]
        return cls(camadas=m["camadas"], dim_oculta=m["dim_oculta"], dim_saida=m["dim_saida"], dropout=m["dropout"],
                   taxa_aprendizado=m["taxa_aprendizado"], decaimento_peso=m["decaimento_peso"], epocas=m["epocas"],
                   paciencia=m["paciencia"], negativos_por_positivo=m["negativos_por_positivo"],
                   fracao_supervisao=m.get("fracao_supervisao", 0.3), peso_auxiliar_exige=m.get("peso_auxiliar_exige", 0.5),
                   dim_texto=cfg["grafo"]["dim_texto_svd"], texto_compartilhado=m.get("texto_compartilhado", True),
                   residual=m.get("residual", True), decodificador_hibrido=m.get("decodificador_hibrido", False),
                   beta_inicial=m.get("beta_inicial", 1.0))


class SAGEHetero:
    def __init__(self, dims_entrada: dict[str, int], hp: Hiper, semente: int):
        self.hp = hp
        rng = np.random.default_rng(semente)
        L = hp.camadas
        d_in = hp.dim_oculta if L > 0 else hp.dim_saida
        glorot = lambda a, b: rng.normal(0.0, np.sqrt(2.0 / (a + b)), size=(a, b))
        p = {}
        self.k_txt = hp.dim_texto if hp.texto_compartilhado else 0
        for t in TIPOS:
            p[f"in.W.{t}"] = glorot(dims_entrada[t] - self.k_txt, d_in)
            p[f"in.b.{t}"] = np.zeros(d_in)
        if self.k_txt:
            # projeção única para os atributos textuais (LSA) de todos os tipos: disciplinas,
            # habilidades e vagas começam no mesmo espaço semântico
            p["in.Wtxt"] = glorot(self.k_txt, d_in)
        if hp.residual and L > 0 and hp.dim_saida != d_in:
            raise ValueError("residual exige dim_saida == dim_oculta")
        dims = [d_in] + [hp.dim_oculta] * (L - 1) + ([hp.dim_saida] if L > 0 else [])
        for l in range(L):
            a, b = dims[l], dims[l + 1]
            for t in TIPOS:
                p[f"l{l}.self.{t}"] = glorot(a, b)
                p[f"l{l}.b.{t}"] = np.zeros(b)
            for r in RELACOES:
                p[f"l{l}.rel.{r[1]}"] = glorot(a, b)
        if hp.decodificador_hibrido:
            # escore = z_d . z_s + beta * similaridade_textual(d, s) + vies
            p["dec.beta"] = np.array([float(hp.beta_inicial)])
            p["dec.vies"] = np.array([-0.5 * float(hp.beta_inicial)])
        self.p = p

    # ---------------------------------------------------------------- forward
    def forward(self, X: dict, M: dict, treino: bool = False, rng: np.random.Generator | None = None):
        p, L, q, k = self.p, self.hp.camadas, self.hp.dropout, self.k_txt
        H = {}
        for t in TIPOS:
            xc = X[t][:, : X[t].shape[1] - k] if k else X[t]
            H[t] = xc @ p[f"in.W.{t}"] + p[f"in.b.{t}"]
            if k:
                H[t] = H[t] + X[t][:, -k:] @ p["in.Wtxt"]
        H0 = H
        cache = {"X": X, "M": M, "camadas": []}
        for l in range(L):
            mascaras = {}
            Hd = {}
            for t in TIPOS:
                if treino and q > 0:
                    mascaras[t] = (rng.random(H[t].shape) >= q) / (1.0 - q)
                    Hd[t] = H[t] * mascaras[t]
                else:
                    Hd[t] = H[t]
            A = {t: Hd[t] @ p[f"l{l}.self.{t}"] + p[f"l{l}.b.{t}"] for t in TIPOS}
            agg = {}
            for r in RELACOES:
                s, nome, d = r
                agg[r] = M[r] @ Hd[s]
                A[d] = A[d] + agg[r] @ p[f"l{l}.rel.{nome}"]
            cache["camadas"].append((Hd, mascaras, agg, A))
            H = {t: (np.maximum(A[t], 0.0) if l < L - 1 else A[t]) for t in TIPOS}
        if L > 0 and self.hp.residual:
            H = {t: H[t] + H0[t] for t in TIPOS}
        return H, cache

    # --------------------------------------------------------------- backward
    def backward(self, G: dict, cache: dict) -> dict:
        p, L, k = self.p, self.hp.camadas, self.k_txt
        M = cache["M"]
        grads = {n: np.zeros_like(v) for n, v in p.items()}
        G_res = G if (L > 0 and self.hp.residual) else None
        for l in reversed(range(L)):
            Hd, mascaras, agg, A = cache["camadas"][l]
            GA = {t: (G[t] * (A[t] > 0) if l < L - 1 else G[t]) for t in TIPOS}
            GH = {t: np.zeros_like(Hd[t]) for t in TIPOS}
            for t in TIPOS:
                grads[f"l{l}.self.{t}"] += Hd[t].T @ GA[t]
                grads[f"l{l}.b.{t}"] += GA[t].sum(0)
                GH[t] += GA[t] @ p[f"l{l}.self.{t}"].T
            for r in RELACOES:
                s, nome, d = r
                W = p[f"l{l}.rel.{nome}"]
                grads[f"l{l}.rel.{nome}"] += agg[r].T @ GA[d]
                GH[s] += M[r].T @ (GA[d] @ W.T)
            G = {t: (GH[t] * mascaras[t] if mascaras else GH[t]) for t in TIPOS}
        if G_res is not None:
            G = {t: G[t] + G_res[t] for t in TIPOS}
        X = cache["X"]
        for t in TIPOS:
            xc = X[t][:, : X[t].shape[1] - k] if k else X[t]
            grads[f"in.W.{t}"] += xc.T @ G[t]
            grads[f"in.b.{t}"] += G[t].sum(0)
            if k:
                grads["in.Wtxt"] += X[t][:, -k:].T @ G[t]
        return grads

    def embeddings(self, X: dict, M: dict) -> dict:
        return self.forward(X, M, treino=False)[0]


# ------------------------------------------------------------------- perda
def perda_enlaces(Z: dict, pos: np.ndarray, neg: np.ndarray, ta: str, tb: str, G: dict, peso: float = 1.0,
                  C: np.ndarray | None = None, p: dict | None = None, gdec: dict | None = None) -> float:
    """Entropia cruzada binária média sobre pares positivos e negativos;
    acumula dL/dZ em G. Com ``C`` (similaridade textual) e os parâmetros do
    decodificador híbrido em ``p``, acumula também dL/dbeta e dL/dvies em ``gdec``."""
    pares = np.vstack([pos, neg])
    y = np.r_[np.ones(len(pos)), np.zeros(len(neg))]
    za, zb = Z[ta][pares[:, 0]], Z[tb][pares[:, 1]]
    logit = (za * zb).sum(1)
    if C is not None:
        c = C[pares[:, 0], pares[:, 1]]
        logit = logit + p["dec.beta"][0] * c + p["dec.vies"][0]
    perda = np.mean(np.logaddexp(0.0, logit) - y * logit)
    dl = peso * (sigmoid(logit) - y) / len(y)
    np.add.at(G[ta], pares[:, 0], dl[:, None] * zb)
    np.add.at(G[tb], pares[:, 1], dl[:, None] * za)
    if C is not None:
        gdec["dec.beta"] += np.array([np.sum(dl * c)])
        gdec["dec.vies"] += np.array([np.sum(dl)])
    return float(peso * perda)


class Adam:
    def __init__(self, params: dict, lr: float, wd: float, b1: float = 0.9, b2: float = 0.999, eps: float = 1e-8):
        self.lr, self.wd, self.b1, self.b2, self.eps, self.t = lr, wd, b1, b2, eps, 0
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}

    def passo(self, params: dict, grads: dict) -> None:
        self.t += 1
        for k in params:
            g = grads[k] + (self.wd * params[k] if (".W" in k or ".self." in k or ".rel." in k) else 0.0)
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * g
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * g * g
            mh = self.m[k] / (1 - self.b1 ** self.t)
            vh = self.v[k] / (1 - self.b2 ** self.t)
            params[k] -= self.lr * mh / (np.sqrt(vh) + self.eps)


def amostrar_negativos(n: int, na: int, nb: int, proibidos: set, rng: np.random.Generator) -> np.ndarray:
    out = []
    tentativas = 0
    while len(out) < n and tentativas < 50 * n + 100:
        a, b = int(rng.integers(na)), int(rng.integers(nb))
        tentativas += 1
        if (a, b) not in proibidos:
            out.append((a, b))
    return np.array(out, dtype=int).reshape(-1, 2)


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """AUC ROC pela estatística de Mann-Whitney (empates valem 1/2)."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    todos = np.r_[pos, neg]
    ordem = todos.argsort(kind="mergesort")
    postos = np.empty(len(todos))
    vals = todos[ordem]
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        postos[ordem[i: j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    rp = postos[: len(pos)].sum()
    return float((rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


@dataclass
class ResultadoTreino:
    modelo: SAGEHetero
    melhor_epoca: int
    historico: list = field(default_factory=list)
    segundos: float = 0.0


def treinar(g: HeteroGrafo, ensina_treino: np.ndarray, ensina_val: np.ndarray | None, hp: Hiper, semente: int,
            epocas_fixas: int | None = None, C: np.ndarray | None = None) -> ResultadoTreino:
    """Treina o modelo. ``ensina_*`` são arrays E x 2 com índices (disciplina, skill);
    ``C`` é a matriz de similaridade textual disciplina x skill (decodificador híbrido)."""
    if hp.decodificador_hibrido and C is None:
        raise ValueError("decodificador híbrido requer a matriz de similaridade textual C")
    C = C if hp.decodificador_hibrido else None
    t0 = time.perf_counter()
    rng = np.random.default_rng(semente)
    X = {t: g.nos[t]["x"] for t in TIPOS}
    modelo = SAGEHetero({t: X[t].shape[1] for t in TIPOS}, hp, semente)
    opt = Adam(modelo.p, hp.taxa_aprendizado, hp.decaimento_peso)
    exige = g.arestas[EXIGE]["index"].T.copy()
    nd, ns, nv = g.num("disciplina"), g.num("skill"), g.num("vaga")
    pos_treino = set(map(tuple, ensina_treino.tolist()))
    pos_exige = set(map(tuple, exige.tolist()))

    M_aval = matrizes_mensagem(g, ensina_treino, exige)
    if ensina_val is not None and len(ensina_val):
        conhecidos = pos_treino | set(map(tuple, ensina_val.tolist()))
        neg_val = np.array([(d, s) for d in range(nd) for s in range(ns) if (d, s) not in conhecidos], dtype=int)

    melhor = (-np.inf, 0, copy.deepcopy(modelo.p))
    historico = []
    sem_melhora = 0
    total = epocas_fixas or hp.epocas
    for ep in range(1, total + 1):
        # divisão mensagem/supervisão da época
        perm = rng.permutation(len(ensina_treino))
        n_sup = max(1, int(round(hp.fracao_supervisao * len(perm))))
        sup, msg = ensina_treino[perm[:n_sup]], ensina_treino[perm[n_sup:]]
        perm_e = rng.permutation(len(exige))
        n_sup_e = max(1, int(round(hp.fracao_supervisao * len(perm_e))))
        sup_e, msg_e = exige[perm_e[:n_sup_e]], exige[perm_e[n_sup_e:]]
        M = matrizes_mensagem(g, msg, msg_e)

        Z, cache = modelo.forward(X, M, treino=True, rng=rng)
        G = {t: np.zeros_like(Z[t]) for t in TIPOS}
        gdec = {k: np.zeros(1) for k in ("dec.beta", "dec.vies")}
        neg = amostrar_negativos(hp.negativos_por_positivo * len(sup), nd, ns, pos_treino, rng)
        perda = perda_enlaces(Z, sup, neg, "disciplina", "skill", G, C=C, p=modelo.p, gdec=gdec)
        if hp.peso_auxiliar_exige > 0:
            neg_e = amostrar_negativos(hp.negativos_por_positivo * len(sup_e), nv, ns, pos_exige, rng)
            perda += perda_enlaces(Z, sup_e, neg_e, "vaga", "skill", G, peso=hp.peso_auxiliar_exige)
        grads = modelo.backward(G, cache)
        if C is not None:
            grads.update(gdec)
        opt.passo(modelo.p, grads)

        reg = {"epoca": ep, "perda": round(perda, 5)}
        if ensina_val is not None and len(ensina_val):
            Ze = modelo.embeddings(X, M_aval)
            S = Ze["disciplina"] @ Ze["skill"].T
            if C is not None:
                S = S + modelo.p["dec.beta"][0] * C + modelo.p["dec.vies"][0]
            a = auc(S[ensina_val[:, 0], ensina_val[:, 1]], S[neg_val[:, 0], neg_val[:, 1]])
            reg["auc_val"] = round(a, 5)
            if a > melhor[0] + 1e-6:
                melhor = (a, ep, copy.deepcopy(modelo.p))
                sem_melhora = 0
            else:
                sem_melhora += 1
            if sem_melhora >= hp.paciencia:
                historico.append(reg)
                break
        historico.append(reg)

    if ensina_val is not None and len(ensina_val):
        modelo.p = melhor[2]
        melhor_ep = melhor[1]
    else:
        melhor_ep = total
    return ResultadoTreino(modelo, melhor_ep, historico, time.perf_counter() - t0)


def escores(modelo: SAGEHetero, g: HeteroGrafo, ensina_visivel: np.ndarray, C: np.ndarray | None = None) -> np.ndarray:
    """Matriz de escores (logits) disciplina x skill, agregando apenas sobre as
    arestas ensina visíveis."""
    X = {t: g.nos[t]["x"] for t in TIPOS}
    M = matrizes_mensagem(g, ensina_visivel, g.arestas[EXIGE]["index"].T)
    Z = modelo.embeddings(X, M)
    S = Z["disciplina"] @ Z["skill"].T
    if modelo.hp.decodificador_hibrido:
        S = S + modelo.p["dec.beta"][0] * C + modelo.p["dec.vies"][0]
    return S
