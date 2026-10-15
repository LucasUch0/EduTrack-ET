"""Confere os gradientes analíticos da GraphSAGE por diferenças finitas."""
import unittest

import numpy as np

from edutrack.graph.hetero import COOC, ENSINA, EXIGE, PREREQ, HeteroGrafo
from edutrack.model.sage import (TIPOS, Hiper, SAGEHetero, auc, matrizes_mensagem, perda_enlaces, treinar)


def grafo_pequeno(semente=0):
    rng = np.random.default_rng(semente)
    g = HeteroGrafo()
    n = {"disciplina": 6, "skill": 8, "vaga": 5}
    f = {"disciplina": 4, "skill": 3, "vaga": 5}
    for t in TIPOS:
        g.nos[t] = {"ids": [f"{t}{i}" for i in range(n[t])], "nomes": [f"{t}{i}" for i in range(n[t])],
                    "x": rng.normal(size=(n[t], f[t]))}
    ens = np.array([[0, 0], [0, 1], [1, 1], [2, 3], [3, 4], [4, 5], [5, 6], [1, 2]]).T
    exi = np.array([[0, 0], [0, 2], [1, 3], [2, 4], [3, 5], [4, 6], [4, 7], [1, 1]]).T
    g.arestas[ENSINA] = {"index": ens, "peso": np.ones(ens.shape[1])}
    g.arestas[EXIGE] = {"index": exi, "peso": np.ones(exi.shape[1])}
    g.arestas[PREREQ] = {"index": np.array([[1, 3], [0, 2]]), "peso": np.ones(2)}
    g.arestas[COOC] = {"index": np.array([[0, 2, 4], [1, 3, 6]]), "peso": np.array([2.0, 3.0, 1.0])}
    return g


class TestGradientes(unittest.TestCase):
    def _perda(self, modelo, X, M, pos, neg, pos_e, neg_e, C=None):
        Z, cache = modelo.forward(X, M, treino=False)
        G = {t: np.zeros_like(Z[t]) for t in TIPOS}
        self.gdec = {k: np.zeros(1) for k in ("dec.beta", "dec.vies")}
        l = perda_enlaces(Z, pos, neg, "disciplina", "skill", G, C=C, p=modelo.p, gdec=self.gdec)
        l += perda_enlaces(Z, pos_e, neg_e, "vaga", "skill", G, peso=0.5)
        return l, G, cache

    def test_gradiente_confere_com_diferencas_finitas(self):
        variantes = [(0, False, False, False), (1, False, False, False), (2, False, False, False), (2, True, True, False),
                     (1, True, True, False), (0, True, False, False), (2, True, True, True)]
        for camadas, compartilhado, residual, hibrido in variantes:
            g = grafo_pequeno()
            d_out = 5 if residual else 4
            hp = Hiper(camadas=camadas, dim_oculta=5, dim_saida=d_out, dropout=0.0, dim_texto=2,
                       texto_compartilhado=compartilhado, residual=residual, decodificador_hibrido=hibrido)
            C = np.random.default_rng(9).random((6, 8)) if hibrido else None
            X = {t: g.nos[t]["x"] for t in TIPOS}
            M = matrizes_mensagem(g, g.arestas[ENSINA]["index"].T, g.arestas[EXIGE]["index"].T)
            modelo = SAGEHetero({t: X[t].shape[1] for t in TIPOS}, hp, semente=3)
            pos = np.array([[0, 0], [2, 3], [5, 6]])
            neg = np.array([[0, 7], [1, 5], [3, 0], [4, 2]])
            pos_e, neg_e = np.array([[0, 2], [3, 5]]), np.array([[1, 7], [2, 0]])
            _, G, cache = self._perda(modelo, X, M, pos, neg, pos_e, neg_e, C)
            grads = modelo.backward(G, cache)
            if hibrido:
                grads.update(self.gdec)
            rng = np.random.default_rng(1)
            eps = 1e-6
            for k in modelo.p:
                idx = tuple(rng.integers(s) for s in modelo.p[k].shape)
                original = modelo.p[k][idx]
                modelo.p[k][idx] = original + eps
                lp, _, _ = self._perda(modelo, X, M, pos, neg, pos_e, neg_e, C)
                modelo.p[k][idx] = original - eps
                lm, _, _ = self._perda(modelo, X, M, pos, neg, pos_e, neg_e, C)
                modelo.p[k][idx] = original
                numerico = (lp - lm) / (2 * eps)
                self.assertAlmostEqual(grads[k][idx], numerico, places=5,
                                       msg=f"variante={camadas, compartilhado, residual, hibrido} parâmetro={k}{idx}")

    def test_treino_reduz_perda_e_e_reprodutivel(self):
        g = grafo_pequeno()
        hp = Hiper(camadas=2, dim_oculta=8, dim_saida=8, epocas=60, paciencia=100, dim_texto=2)
        ens = g.arestas[ENSINA]["index"].T
        r1 = treinar(g, ens, None, hp, semente=7)
        r2 = treinar(g, ens, None, hp, semente=7)
        self.assertLess(np.mean([h["perda"] for h in r1.historico[-10:]]), np.mean([h["perda"] for h in r1.historico[:10]]))
        for k in r1.modelo.p:  # RF40: mesma semente, mesmos pesos
            np.testing.assert_array_equal(r1.modelo.p[k], r2.modelo.p[k])

    def test_auc(self):
        self.assertEqual(auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])), 1.0)
        self.assertEqual(auc(np.array([1.0]), np.array([1.0])), 0.5)
        self.assertAlmostEqual(auc(np.array([2.0, 0.0]), np.array([1.0])), 0.5)


if __name__ == "__main__":
    unittest.main()
