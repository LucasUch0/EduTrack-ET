"""Coleta (RF04, RF41) com HTML de exemplo, sem acesso à rede."""
import unittest

from edutrack.collect.scrape_talent import ids_da_busca, limpar, parse_vaga
from edutrack.normalize.pipeline import chave_duplicata, funcao_nao_tecnica

PAGINA_VAGA = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},{"@type":"JobPosting","title":"Analista de Dados",
"description":"<p>Requisitos: SQL e Python.</p><p>Contato: rh@empresa.com.br ou (92) 99999-1234</p>",
"datePosted":"2026-10-01","hiringOrganization":{"name":"Empresa X"},
"jobLocation":{"address":{"addressLocality":"Manaus","addressRegion":"State of Amazonas"}}}]}
</script></head><body></body></html>"""

PAGINA_BUSCA = """<div data-testid="jobcard-container-123"><h2>Desenvolvedor Java</h2></div>
<div data-testid="jobcard-container-456"><h2>Analista de RH</h2></div>"""


class TestColeta(unittest.TestCase):
    def test_parse_json_ld_e_remocao_de_dados_pessoais(self):
        v = parse_vaga(PAGINA_VAGA, "999")
        self.assertEqual((v["titulo"], v["empresa"], v["cidade"], v["data_publicacao"]),
                         ("Analista de Dados", "Empresa X", "Manaus", "2026-10-01"))
        self.assertNotIn("rh@empresa.com.br", v["descricao"])
        self.assertNotIn("99999-1234", v["descricao"])
        self.assertIn("SQL e Python", v["descricao"])
        self.assertEqual(v["url"], "https://br.talent.com/view?id=999")

    def test_ids_da_busca(self):
        self.assertEqual(ids_da_busca(PAGINA_BUSCA), [("123", "Desenvolvedor Java"), ("456", "Analista de RH")])

    def test_limpar(self):
        self.assertEqual(limpar("ligue (92) 3333-4444 ou veja https://x.com"), "ligue [telefone removido] ou veja [link removido]")

    def test_duplicatas_e_funcoes_nao_tecnicas(self):  # RF05
        self.assertEqual(chave_duplicata("[1310] Dev Java - 117063", "Sidia Instituto"), chave_duplicata("Dev Java", "SIDIA"))
        self.assertTrue(funcao_nao_tecnica("Vendedor - Produtos de Tecnologia"))
        self.assertFalse(funcao_nao_tecnica("Desenvolvedor Android"))


if __name__ == "__main__":
    unittest.main()
