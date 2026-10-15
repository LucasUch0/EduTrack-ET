"""Motor de recomendação e diagnóstico (RF26–RF35, RN03, RN05)."""
import unittest

from edutrack.recommend.engine import Base, ErroEntrada


class TestTrilha(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Base.carregar()
        cls.ate3 = [d["id"] for d in cls.b.disciplinas if d["periodo"] <= 3]

    def test_aderencia_cresce_e_respeita_teto(self):
        r = self.b.trilha(self.ate3)
        self.assertLessEqual(r["aderencia_antes"], r["aderencia_depois"])
        self.assertLessEqual(r["aderencia_depois"], r["aderencia_teto_curricular"] + 1e-9)
        self.assertEqual(r["k"], 5)  # RN05

    def test_pre_requisitos_respeitados(self):  # RN03
        for k in (1, 3, 5, 10):
            r = self.b.trilha([], "desenvolvimento", k, "gnn")
            vistas = set()
            for it in r["trilha"]:
                for p in it["pre_requisitos"]:
                    self.assertIn(p, vistas, f"{it['disciplina']} antes de {p} (k={k})")
                vistas.add(it["disciplina"])
            self.assertLessEqual(len(r["trilha"]), k)

    def test_nao_recomenda_cursadas(self):
        r = self.b.trilha(self.ate3)
        self.assertFalse({i["disciplina"] for i in r["trilha"]} & set(self.ate3))

    def test_entradas_invalidas(self):
        with self.assertRaises(ErroEntrada):
            self.b.trilha(["nao_existe"])
        with self.assertRaises(ErroEntrada):
            self.b.trilha([], perfil="astronauta")
        with self.assertRaises(ErroEntrada):
            self.b.trilha([], k=50)

    def test_perfil_restringe_vagas(self):  # RF31
        r = self.b.trilha([], "dados_ia")
        self.assertEqual(r["vagas_consideradas"], sum(1 for v in self.b.vagas if v["perfil"] == "dados_ia"))

    def test_diagnostico(self):  # RF32–RF34
        d = self.b.diagnostico()
        self.assertTrue(all(x["id"] not in self.b.ensinadas for x in d["lacunas"]))
        demandas = [x["demanda"] for x in d["lacunas"]]
        self.assertEqual(demandas, sorted(demandas, reverse=True))
        self.assertTrue(self.b.diagnostico_csv().startswith("﻿situacao;"))

    def test_apoio_corroborado_pelo_mercado(self):
        """Toda disciplina de apoio sugerida ensina uma habilidade que as vagas pedem junto com a lacuna."""
        sugestoes = 0
        for x in self.b.diagnostico()["lacunas"]:
            apoio = self.b.apoio_estrutural(x["id"])
            if apoio is None:
                continue
            sugestoes += 1
            self.assertTrue(apoio["ponte"], x["id"])
            for p in apoio["ponte"]:
                self.assertIn(p["id"], self.b.ensina[apoio["disciplina"]])
                self.assertGreaterEqual(self.b.coocorrencia[(x["id"], p["id"])], 2)
            self.assertGreaterEqual(apoio["afinidade"], 0.15)
            self.assertFalse(apoio["validada"])
        self.assertGreater(sugestoes, 0)

    def test_afinidade_rf26(self):
        r = self.b.afinidade_disciplinas(["sql"], "tfidf", 3)
        self.assertEqual(r["disciplinas"][0]["disciplina"], "manipulacao_bd")
        for modelo in ("tfidf", "gnn"):  # estágio, TCC e optativa ficam fora, como na trilha
            ids = {x["disciplina"] for x in self.b.afinidade_disciplinas(["sql", "cloud"], modelo, 40)["disciplinas"]}
            self.assertFalse(ids & {"estagio", "tcc", "optativa"}, modelo)


if __name__ == "__main__":
    unittest.main()
