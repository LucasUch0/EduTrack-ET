"""Normalização semântica (RF11–RF16) e extração do PPC (RF07–RF10a)."""
import unittest

from edutrack.config import caminho
from edutrack.normalize.normalize_skills import Normalizador, Ontologia, variacao_morfologica
from edutrack.parse.parse_ppc import corrigir_espacamento, parse_bloco, segmentar


class TestOntologia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ont = Ontologia(caminho("ontologia"))
        cls.n = Normalizador(cls.ont, limiar=0.87)

    def test_tamanho(self):
        self.assertEqual(len(self.ont.habilidades), 76)
        self.assertEqual(len(self.ont.categorias), 9)

    def test_sinonimos_de_python_resolvem_para_o_mesmo_canonico(self):  # exemplo do Parecer
        for termo in ("Python", "Python 3", "Linguagem Python", "python3"):
            sid, camada, _, _ = self.n.normalizar_termo(termo)
            self.assertEqual(sid, "python", termo)
            self.assertEqual(camada, "exata")

    def test_maior_ocorrencia_vence(self):
        hab, _ = self.n.habilidades_de("Experiência com Power BI e JavaScript.")
        self.assertIn("bi", hab)
        self.assertIn("javascript", hab)
        self.assertNotIn("java", hab)

    def test_camada_aproximada_aceita_variacoes(self):
        for termo, esperado in (("SpringBoot", "spring"), ("Power Shell", "windows_server"),
                                ("Diagramas de atividade", "uml_modelagem"), ("engenharia de prompts", "genai")):
            sid, camada, escore, _ = self.n.normalizar_termo(termo)
            self.assertEqual((sid, camada), (esperado, "fuzzy"), termo)
            self.assertGreaterEqual(escore, 0.87)

    def test_camada_aproximada_rejeita_falsos_positivos(self):  # casos reais que a razão pura aceitava
        for termo in ("Formação", "Supervisor", "Elétrica", "restore", "linguagem Rust", "validação de dados"):
            sid, _, _, _ = self.n.normalizar_termo(termo)
            self.assertIsNone(sid, termo)

    def test_sigla_em_titulo_maiusculo_nao_conta(self):
        hab, _ = self.n.habilidades_de("OP DE MÁQUINA IA SR.\nOperar máquinas de inserção.")
        self.assertNotIn("ia_fundamentos", hab)
        hab, _ = self.n.habilidades_de("Projetos com IA aplicada à indústria.")
        self.assertIn("ia_fundamentos", hab)

    def test_trilha_de_auditoria(self):  # RF14
        oc = self.n.extrair("Conhecimento em SQL e Docker.", "v1")
        res = {o.skill_id: o for o in oc if o.skill_id}
        self.assertEqual(res["sql"].termo_original, "SQL")
        self.assertEqual(res["containers"].camada, "exata")
        self.assertTrue(all(o.doc_id == "v1" for o in oc))

    def test_variacao_morfologica(self):
        self.assertTrue(variacao_morfologica("eletronico", "eletronica"))
        self.assertTrue(variacao_morfologica("diagramas", "diagrama"))
        self.assertFalse(variacao_morfologica("supervisor", "supervisorio"))
        self.assertFalse(variacao_morfologica("formacao", "formatacao"))


class TestPPC(unittest.TestCase):
    BLOCO = ("DISCIPLINA: COMPILADORES CÓDIGO: 25782 Nº CRÉDITOS: 3 CARGA HORÁRIA: 66\n"
             "CURSO: CIÊNCIA DA COMPUTAÇÃO CURRÍCULO: CCO-2024/1 SEDE PRESENCIAL GRAU: BACHARELADO PERÍODO: 7\n"
             "EMENTA\nCompiladores e Interpretadores. Análise Léxica e Sintática.\nBIBLIOGRAFIA BÁSICA\n"
             "1. AHO, Alfred. Compiladores. 2.ed. São Paulo: Pearson, 2008.\nBIBLIOGRAFIA COMPLEMENTAR\n"
             "1. COOPER, Keith. Construindo compiladores. Rio de Janeiro: Elsevier, 2014.\n")

    def test_parse_bloco(self):
        d = parse_bloco(self.BLOCO)
        self.assertEqual((d["nome"], d["codigo"], d["creditos"], d["carga_horaria"], d["periodo"]),
                         ("COMPILADORES", "25782", 3, 66, 7))
        self.assertTrue(d["ementa"].startswith("Compiladores e Interpretadores"))
        self.assertEqual(len(d["bibliografia_basica"]), 1)

    def test_segmentacao_e_descarte_de_espurios(self):  # RF07, RF09
        blocos = segmentar("lixo inicial\n" + self.BLOCO + "DISCIPLINA: X\n")
        validos = [b for b in blocos if parse_bloco(b)]
        self.assertEqual(len(validos), 1)

    def test_corrige_palavras_coladas_do_pdf(self):
        self.assertEqual(corrigir_espacamento("Pesquisa deMercado.Técnicas de Vendas"), "Pesquisa de Mercado. Técnicas de Vendas")


if __name__ == "__main__":
    unittest.main()
