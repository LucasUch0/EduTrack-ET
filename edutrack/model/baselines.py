"""Linhas de base não neurais (RF37), avaliadas nas mesmas partições da GNN.

* TF-IDF: similaridade de cossenos entre o texto da disciplina (nome +
  ementa) e o documento da habilidade (nome + sinônimos da ontologia).
* Popularidade: ordena as disciplinas pelo número de habilidades que já
  ensinam no treino — referência mínima que qualquer modelo deve superar.
* Coocorrência (heurística de grafo): afinidade média entre a habilidade-alvo
  e as habilidades que a disciplina já ensina, com a coocorrência nas vagas
  normalizada pelo cosseno. Mostra quanto da estrutura do grafo é capturado
  sem aprendizado.
"""
from __future__ import annotations

import numpy as np

from edutrack.graph.hetero import EXIGE, documento_skill, vetorizador_tfidf


def tfidf(textos_disciplina: list[str], ont, textos_vaga: list[str]) -> np.ndarray:
    docs_skill = [documento_skill(h) for h in ont.habilidades.values()]
    vec = vetorizador_tfidf().fit(textos_disciplina + docs_skill + textos_vaga)
    a = vec.transform(textos_disciplina)
    b = vec.transform(docs_skill)
    return (a @ b.T).toarray()  # vetores já normalizados (norma L2) => cosseno


def popularidade(ensina_treino: np.ndarray, nd: int, ns: int) -> np.ndarray:
    grau = np.bincount(ensina_treino[:, 0], minlength=nd).astype(float)
    return np.repeat(grau[:, None], ns, axis=1)


def coocorrencia(g, ensina_treino: np.ndarray) -> np.ndarray:
    nd, ns, nv = g.num("disciplina"), g.num("skill"), g.num("vaga")
    ex = g.arestas[EXIGE]["index"]
    B = np.zeros((nv, ns))
    B[ex[0], ex[1]] = 1.0
    C = B.T @ B
    f = np.sqrt(np.diag(C))
    f[f == 0] = 1.0
    C = C / f[:, None] / f[None, :]
    np.fill_diagonal(C, 0.0)
    A = np.zeros((nd, ns))
    A[ensina_treino[:, 0], ensina_treino[:, 1]] = 1.0
    grau = A.sum(1, keepdims=True)
    grau[grau == 0] = 1.0
    return (A @ C) / grau
