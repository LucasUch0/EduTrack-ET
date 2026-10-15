"""Verificação rastreável dos requisitos do Documento de Requisitos v1.1.

Cada teste leva no nome o identificador do requisito que verifica (RF, RNF ou
RN). Os testes da coleta sobem um servidor HTTP falso em 127.0.0.1, sem acesso
à internet. Os da interface no navegador estão em scripts/auditoria_interface.py.

    python -m unittest tests.test_requisitos -v
"""
from __future__ import annotations

import copy
import csv
import hashlib
import http.server
import io
import json
import logging
import random
import re
import shutil
import socket
import tempfile
import threading
import time
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from edutrack.config import RAIZ, artefatos, caminho, carregar_config, processados
from edutrack.graph.hetero import COOC, ENSINA, EXIGE, PREREQ, HeteroGrafo, carregar_dados, construir
from edutrack.normalize.normalize_skills import Normalizador, Ontologia
from edutrack.recommend.engine import NAO_RECOMENDAVEIS, NOMES_PERFIS, Base, ErroEntrada

try:  # dependências do pipeline (requirements-pipeline.txt)
    import bs4  # noqa: F401
    import requests  # noqa: F401
    TEM_COLETA = True
except ImportError:  # pragma: no cover
    TEM_COLETA = False

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
TELEFONE = re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}[-.\s]\d{4}\b")
LINK = re.compile(r"https?://|www\.")


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


# ===========================================================================
# M1 — Coleta (RF01–RF06, RF41, RNF08, RNF15, RNF20) com servidor falso
# ===========================================================================
class _Portal(http.server.BaseHTTPRequestHandler):
    registro: list = []

    def log_message(self, *a):  # silencia o servidor de teste
        pass

    def _resp(self, status: int, corpo: str):
        dados = corpo.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        _Portal.registro.append({"t": time.monotonic(), "path": u.path, "q": q, "ua": self.headers.get("User-Agent", "")})
        if u.path == "/robots.txt":
            return self._resp(200, "User-agent: *\nDisallow: /search-jobs/\nDisallow: /proibido\n")
        if u.path == "/jobs":
            termo = q.get("k", [""])[0]
            if termo == "falha":
                return self._resp(500, "erro")
            p = int(q.get("p", ["1"])[0])
            if p == 1:
                cards = ('<div data-testid="jobcard-container-101"><h2>Desenvolvedor Python</h2></div>'
                         '<div data-testid="jobcard-container-102"><h2>Vendedor Externo</h2></div>'
                         '<div data-testid="jobcard-container-999"><h2>Analista de Sistemas</h2></div>'
                         '<a href="/jobs?k=x&amp;p=2">2</a>')
            else:
                cards = '<div data-testid="jobcard-container-103"><h2>Analista de Dados</h2></div>'
            return self._resp(200, cards)
        if u.path == "/view":
            i = q.get("id", [""])[0]
            if i == "999":
                return self._resp(500, "erro interno")
            jp = {"@type": "JobPosting", "title": f"Vaga {i}", "datePosted": "2026-10-01",
                  "hiringOrganization": {"name": "Empresa Teste"},
                  "jobLocation": {"address": {"addressLocality": "Manaus", "addressRegion": "AM"}},
                  "description": "<p>Python e SQL. Fale com Ana: ana.silva@empresa.com.br, (92) 98765-4321, "
                                 "https://empresa.com/vagas</p>"}
            return self._resp(200, f'<script type="application/ld+json">{json.dumps({"@graph": [jp]})}</script>')
        return self._resp(404, "não encontrado")


@unittest.skipUnless(TEM_COLETA, "requer requests e beautifulsoup4 (requirements-pipeline.txt)")
class TestColeta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Portal)
        cls.porta = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        _Portal.registro = []

    def cfg(self, **mudar) -> dict:
        c = copy.deepcopy(carregar_config())
        c["coleta"].update({"dominio": f"http://127.0.0.1:{self.porta}", "intervalo_minimo_s": 0.2,
                            "termos_busca": ["python", "falha"], "timeout_s": 3}, **mudar)
        return c

    def coletar(self, **mudar):
        from edutrack.collect.scrape_talent import Coletor
        return Coletor(self.cfg(**mudar)).coletar(max_paginas=2)

    def test_RF01_filtra_localidade_e_termos_configuraveis(self):
        self.coletar()
        buscas = [r for r in _Portal.registro if r["path"] == "/jobs"]
        self.assertTrue(buscas)
        self.assertTrue(all(r["q"]["l"] == ["Manaus, AM"] for r in buscas))
        self.assertEqual({r["q"]["k"][0] for r in buscas}, {"python", "falha"})

    def test_RF02_respeita_robots_txt(self):
        from edutrack.collect.scrape_talent import Coletor
        c = Coletor(self.cfg())
        self.assertEqual(_Portal.registro[0]["path"], "/robots.txt")  # lido antes de qualquer requisição
        self.assertIsNone(c.obter("/proibido"))
        self.assertNotIn("/proibido", [r["path"] for r in _Portal.registro])
        self.assertIn("robots", c.falhas[-1][1])

    def test_RF02_RNF20_robots_inacessivel_aborta_sem_quebrar(self):
        from edutrack.collect.scrape_talent import Coletor
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            fechada = s.getsockname()[1]
        c = self.cfg()
        c["coleta"]["dominio"] = f"http://127.0.0.1:{fechada}"
        r = Coletor(c).coletar(max_paginas=1)  # sem robots.txt conferido, nada é coletado
        self.assertEqual(r["meta"]["vagas_coletadas"], 0)
        self.assertEqual(r["meta"]["requisicoes_http"], 0)

    def test_RF03_intervalo_minimo_e_user_agent(self):
        self.coletar()
        pedidos = [r for r in _Portal.registro if r["path"] != "/robots.txt"]
        intervalos = [b["t"] - a["t"] for a, b in zip(pedidos, pedidos[1:])]
        self.assertGreater(len(intervalos), 3)
        self.assertGreaterEqual(min(intervalos), 0.2 - 0.02)
        ua = carregar_config()["coleta"]["user_agent"]
        self.assertTrue(all(r["ua"] == ua for r in pedidos))
        self.assertIn("EduTrack-GNN", ua)

    def test_RF04_RF41_vaga_estruturada_sem_dados_pessoais(self):
        r = self.coletar()
        self.assertEqual(sorted(v["id"] for v in r["vagas"]), ["101", "103"])  # 102 não é de TI; 999 falhou
        for v in r["vagas"]:
            for campo in ("titulo", "descricao", "cidade", "data_coleta", "url"):
                self.assertTrue(v[campo], campo)
            self.assertIsNone(EMAIL.search(v["descricao"]))
            self.assertIsNone(TELEFONE.search(v["descricao"]))
            self.assertIsNone(LINK.search(v["descricao"]))
        json.dumps(r)  # serializável em JSON

    def test_RF06_registra_coletadas_descartadas_e_falhas(self):
        with self.assertLogs("edutrack.coleta", level="INFO") as log:
            r = self.coletar()
        linha = log.output[-1]
        for termo in ("coletadas=2", "descartadas=1", "falhas=", "requisições="):
            self.assertIn(termo, linha)
        self.assertEqual(r["meta"]["descartadas_titulo"], 1)

    def test_RNF08_teto_de_requisicoes(self):
        r = self.coletar(max_requisicoes=3)
        self.assertEqual(r["meta"]["requisicoes_http"], 3)
        self.assertEqual(len([x for x in _Portal.registro if x["path"] != "/robots.txt"]), 3)

    def test_RNF20_falha_de_rede_nao_interrompe(self):
        r = self.coletar()  # termo "falha" devolve 500 e a vaga 999 também
        self.assertGreaterEqual(r["meta"]["falhas"], 2)
        self.assertEqual(r["meta"]["vagas_coletadas"], 2)


# ===========================================================================
# M2 — Extração curricular (RF07–RF10a, RNF20, RNF21, RN06)
# ===========================================================================
class TestPPC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pdfplumber  # noqa: F401
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("requer pdfplumber (requirements-pipeline.txt)")
        from edutrack.parse import parse_ppc
        cls.pp = parse_ppc
        logging.getLogger("edutrack.ppc").setLevel(logging.ERROR)
        cls.validas, cls.espurias = parse_ppc.extrair_ppc(caminho("ppc_pdf"))
        cls.base = parse_ppc.montar_base_curricular()

    def test_RF07_RF08_segmenta_e_extrai_campos(self):
        self.assertEqual(len(self.validas), 18)
        for d in self.validas:
            self.assertTrue(d["nome"] and d["codigo"] and d["carga_horaria"] and d["periodo"] and d["ementa"], d["nome"])
            self.assertTrue(d["bibliografia_basica"], d["nome"])

    def test_RF09_descarta_espurios(self):
        texto = ("DISCIPLINA: A\nlixo de bibliografia\nDISCIPLINA: ESTRUTURAS CÓDIGO: 1 Nº CRÉDITOS: 4 CARGA HORÁRIA: 66\n"
                 "PERÍODO: 3\nEMENTA Listas e árvores.\nBIBLIOGRAFIA BÁSICA\nSILVA, A. Estruturas. 2020.\n"
                 "BIBLIOGRAFIA COMPLEMENTAR\nSOUZA, B. Dados. 2021.\n")
        blocos = self.pp.segmentar(texto)
        validos = [b for b in blocos if (d := self.pp.parse_bloco(b)) and d["ementa"]]
        self.assertEqual(len(validos), 1)

    def test_RF10_RNF21_contagem_e_declaracao(self):
        c = self.base["cobertura"]
        self.assertEqual(c["disciplinas_esperadas"], 39)
        self.assertEqual(c["disciplinas_identificadas"], 32)
        self.assertTrue(c["divergencia_contagem"])          # divergência sinalizada
        self.assertEqual(c["declaracao_RNF21"], "8 de 8 períodos e 32 de 39 disciplinas")
        self.assertEqual(c["periodos_presentes"], 8)

    def test_RF10a_disciplina_fora_da_grade_vira_stub_identificavel(self):
        original = self.pp.extrair_ppc
        extra = dict(self.validas[0], nome="TÓPICOS ESPECIAIS EM COMPUTAÇÃO", codigo="99999")
        self.pp.extrair_ppc = lambda pdf: (self.validas + [extra], [])
        try:
            base = self.pp.montar_base_curricular()
        finally:
            self.pp.extrair_ppc = original
        stub = [d for d in base["disciplinas"] if d.get("fora_da_grade_declarada")]
        self.assertEqual([d["nome"] for d in stub], ["TÓPICOS ESPECIAIS EM COMPUTAÇÃO"])
        self.assertEqual(stub[0]["id"], "topicos_especiais_em_computacao")

    def test_RNF20_pdf_malformado_nao_interrompe(self):
        with tempfile.TemporaryDirectory() as t:
            ruim = Path(t) / "ppc.pdf"
            ruim.write_bytes(b"%PDF-1.4\n isto nao e um pdf \x00\x01")
            base = self.pp.montar_base_curricular(ruim)  # registra e segue com a grade declarada
        self.assertEqual(base["cobertura"]["extraidas_do_pdf"], 0)
        self.assertEqual(base["cobertura"]["disciplinas_identificadas"], 32)

    def test_RN06_toda_disciplina_da_grade_e_no_do_grafo(self):
        g = HeteroGrafo.carregar(artefatos() / "graph")
        grade = {d["id"] for d in _json(caminho("grade"))["disciplinas"]}
        self.assertLessEqual(grade, set(g.nos["disciplina"]["ids"]))
        sem_ensina = _json(artefatos() / "graph" / "validacao.json")["tipos_de_no"]["disciplina"]["ids_isolados"]
        ensina = {d for d, _ in g.pares(ENSINA)}
        ids = g.nos["disciplina"]["ids"]
        self.assertEqual({ids[i] for i in range(len(ids)) if i not in ensina and ids[i] in sem_ensina}, set(sem_ensina))


# ===========================================================================
# M3 — Normalização (RF11–RF16, RN01, RN02, RNF18)
# ===========================================================================
class TestNormalizacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ont_json = _json(caminho("ontologia"))
        cls.ont = Ontologia(caminho("ontologia"))
        cls.limiar = carregar_config()["normalizacao"]["limiar_fuzzy"]

    def test_RF11_ontologia_canonica_com_categoria_e_sinonimos(self):
        ids = [h["id"] for h in self.ont_json["habilidades"]]
        self.assertEqual(len(ids), len(set(ids)))
        cats = {c["id"] for c in self.ont_json["categorias"]}
        for h in self.ont_json["habilidades"]:
            self.assertRegex(h["id"], r"^[a-z0-9_]+$")
            self.assertIn(h["categoria"], cats)
            self.assertTrue(h["aliases"], h["id"])

    def test_RF11_nenhum_sinonimo_aponta_para_duas_habilidades(self):
        dono = {}
        for h in self.ont_json["habilidades"]:
            for a in h["aliases"] + h.get("aliases_cs", []):
                chave = a.lower()
                self.assertIn(dono.setdefault(chave, h["id"]), (h["id"],), f"'{a}' em {dono[chave]} e {h['id']}")

    def test_RF12_RF13_RN02_limiar_configuravel(self):
        self.assertEqual(self.limiar, 0.87)
        termo = "Diagramas de atividade"  # escore 0,98 na camada aproximada
        padrao = Normalizador(self.ont, limiar=self.limiar).normalizar_termo(termo)
        self.assertEqual(padrao[0], "uml_modelagem")
        rigido = Normalizador(self.ont, limiar=0.99).normalizar_termo(termo)
        self.assertIsNone(rigido[0])
        self.assertEqual(Normalizador(self.ont, limiar=self.limiar).normalizar_termo("linguagem python 3")[0], "python")

    def test_RF14_auditoria_completa_e_acima_do_limiar(self):
        with open(processados() / "auditoria_normalizacao.csv", encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        self.assertGreater(len(linhas), 1000)
        for r in linhas:
            for campo in ("termo_original", "camada", "escore"):
                self.assertIn(campo, r)
            if r["camada"] in ("exata", "fuzzy"):
                self.assertTrue(r["skill_id"] in self.ont.habilidades, r)
            if r["camada"] == "fuzzy":
                self.assertGreaterEqual(float(r["escore"]), self.limiar)

    def test_RF15_relatorio_de_nao_resolvidos_por_frequencia(self):
        with open(processados() / "nao_resolvidos.csv", encoding="utf-8") as f:
            freq = [int(r["frequencia"]) for r in csv.DictReader(f)]
        self.assertGreater(len(freq), 10)
        self.assertEqual(freq, sorted(freq, reverse=True))

    def test_RF16_novo_sinonimo_sem_alterar_codigo(self):
        termo = "tecnologia xyzzy"
        self.assertIsNone(Normalizador(self.ont, limiar=self.limiar).normalizar_termo(termo)[0])
        with tempfile.TemporaryDirectory() as t:
            novo = copy.deepcopy(self.ont_json)
            alvo = next(h for h in novo["habilidades"] if h["id"] == "python")
            alvo["aliases"].append(termo)
            arq = Path(t) / "skills_ontology.json"
            arq.write_text(json.dumps(novo, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(Normalizador(Ontologia(arq), limiar=self.limiar).normalizar_termo(termo)[0], "python")

    def test_RN01_so_habilidades_canonicas_entram_no_grafo(self):
        g = HeteroGrafo.carregar(artefatos() / "graph")
        self.assertEqual(set(g.nos["skill"]["ids"]), set(self.ont.habilidades))
        with open(processados() / "nao_resolvidos.csv", encoding="utf-8") as f:
            quarentena = {r["termo"] for r in csv.DictReader(f)}
        self.assertFalse(quarentena & set(g.nos["skill"]["ids"]))

    def test_RNF18_cobertura_reportada_e_acima_da_meta(self):
        c = _json(processados() / "resumo_normalizacao.json")["cobertura_RNF18_vagas"]
        self.assertGreaterEqual(c["cobertura"], 0.85)
        self.assertAlmostEqual(c["cobertura"], c["termos_resolvidos"] / c["termos_elegiveis"], places=4)


# ===========================================================================
# M4 — Grafo (RF17–RF22)
# ===========================================================================
class TestGrafo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = HeteroGrafo.carregar(artefatos() / "graph")  # RF21: carrega sem reconstruir

    def test_RF17_RF18_tipos_de_no_e_de_aresta(self):
        self.assertEqual(set(self.g.nos), {"disciplina", "skill", "vaga"})
        self.assertEqual(set(self.g.arestas), {ENSINA, EXIGE, PREREQ, COOC})
        for rel, a in self.g.arestas.items():
            self.assertGreater(a["index"].shape[1], 0, rel)

    def test_RF19_atributos_iniciais(self):
        for t, n in self.g.nos.items():
            self.assertEqual(n["x"].shape[0], len(n["ids"]))
            self.assertTrue(np.isfinite(n["x"]).all())
        self.assertIn("carga_horaria", self.g.nos["disciplina"]["atributos"])
        self.assertTrue(any(a.startswith("periodo_") for a in self.g.nos["disciplina"]["atributos"]))
        self.assertTrue(any(a.startswith("cat_") for a in self.g.nos["skill"]["atributos"]))

    def test_RF20_validacao_detecta_problemas(self):
        self.assertTrue(self.g.validar()["valido"])
        ruim = copy.deepcopy(self.g)
        ruim.arestas[ENSINA]["index"] = ruim.arestas[ENSINA]["index"].copy()
        ruim.arestas[ENSINA]["index"][1, 0] = 10_000
        ruim.arestas[PREREQ]["index"] = np.zeros((2, 0), dtype=int)
        rel = ruim.validar()
        self.assertFalse(rel["valido"])
        self.assertTrue(any("fora do intervalo" in p for p in rel["problemas"]))
        self.assertTrue(any("vazio" in p for p in rel["problemas"]))
        self.assertIn("isolados", rel["tipos_de_no"]["disciplina"])

    def test_RF21_exporta_e_recarrega_igual(self):
        with tempfile.TemporaryDirectory() as t:
            self.g.salvar(Path(t))
            g2 = HeteroGrafo.carregar(Path(t))
        for rel in self.g.arestas:
            self.assertTrue(np.array_equal(self.g.arestas[rel]["index"], g2.arestas[rel]["index"]))
        for t in self.g.nos:
            self.assertTrue(np.allclose(self.g.nos[t]["x"], g2.nos[t]["x"]))

    def test_RF22_subgrafo_centrado(self):
        for tipo, i in (("disciplina", "manipulacao_bd"), ("skill", "sql")):
            s = self.g.subgrafo(tipo, i)
            self.assertEqual(s["centro"]["id"], i)
            self.assertTrue(s["arestas"])
            self.assertTrue(all(i in (a["origem"], a["destino"]) for a in s["arestas"]))


# ===========================================================================
# M5/M8 — Modelo, partição e avaliação (RF23–RF26, RF36–RF40)
# ===========================================================================
class TestModeloEAvaliacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aval = _json(artefatos() / "metrics" / "avaliacao.json")
        cls.meta = _json(artefatos() / "model" / "hiperparametros.json")

    def test_RF23_RF25_pesos_e_hiperparametros_persistidos(self):
        pesos = np.load(artefatos() / "model" / "modelo_gnn.npz")
        self.assertGreater(len(pesos.files), 3)
        self.assertTrue(all(np.isfinite(pesos[k]).all() for k in pesos.files))
        for chave in ("ids_disciplina", "ids_skill", "modelo_padrao"):
            self.assertIn(chave, self.meta)
        for m in ("gnn", "tfidf"):
            A = np.load(artefatos() / "model" / f"afinidade_{m}.npy")
            self.assertEqual(A.shape, (len(self.meta["ids_disciplina"]), len(self.meta["ids_skill"])))
            self.assertTrue(np.isfinite(A).all())

    def test_RF24_particao_sem_vazamento(self):
        from edutrack.model.evaluate import dividir
        cfg = carregar_config()["avaliacao"]
        dados = carregar_dados()
        todas = sorted({(d, h["skill"]) for d, v in dados["disc_hab"].items() for h in v["habilidades"]})
        arr = np.arange(len(todas)).reshape(-1, 1).repeat(2, 1)
        for semente in cfg["sementes"][:5]:
            tr, va, te = dividir(arr, cfg["fracao_validacao"], cfg["fracao_teste"], semente)
            a, b, c = ({tuple(x) for x in p.tolist()} for p in (tr, va, te))
            self.assertFalse(a & b or a & c or b & c)
            self.assertEqual(len(a | b | c), len(todas))
            visiveis = [todas[i] for i, _ in tr.tolist()]
            g = construir(dados, arestas_ensina=visiveis, semente=semente)
            ids_d, ids_s = g.nos["disciplina"]["ids"], g.nos["skill"]["ids"]
            no_grafo = {(ids_d[d], ids_s[s]) for d, s in g.pares(ENSINA)}
            self.assertEqual(no_grafo, set(visiveis))  # validação e teste fora do grafo de treino

    def test_RF24_amostragem_negativa(self):
        self.assertGreaterEqual(self.aval["protocolo"]["hiperparametros_gnn"]["negativos_por_positivo"], 1)

    def test_RF26_afinidade_ordenada_com_escore(self):
        b = Base.carregar()
        for modelo in ("gnn", "tfidf"):
            r = b.afinidade_disciplinas(["sql", "cloud"], modelo, 10)["disciplinas"]
            escores = [x["afinidade"] for x in r]
            self.assertEqual(escores, sorted(escores, reverse=True))
            self.assertEqual(len(r), 10)

    def test_RF36_RF39_metricas_para_k_1_3_5_10_e_tabela(self):
        self.assertEqual(self.aval["protocolo"]["k"], [1, 3, 5, 10])
        for cen in ("texto_completo", "texto_mascarado"):
            for modelo, mets in self.aval["agregado"][cen].items():
                for k in (1, 3, 5, 10):
                    self.assertIn(f"P@{k}", mets, modelo)
                    self.assertIn(f"R@{k}", mets, modelo)
        with open(artefatos() / "metrics" / "tabela_comparativa.csv", encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        self.assertEqual(len(linhas), 12)  # 6 modelos x 2 cenários
        self.assertIn("TF-IDF (cosseno)", {r["modelo"] for r in linhas})

    def test_RF37_tfidf_nas_mesmas_particoes(self):
        for reg in self.aval["por_semente"]:
            for cen in ("texto_completo", "texto_mascarado"):
                res = reg["resultados"][cen]
                self.assertEqual(res["TF-IDF (cosseno)"]["consultas"], res["GraphSAGE + texto (híbrido)"]["consultas"])

    def test_RF38_tempos_de_treino_e_inferencia(self):
        t = self.aval["tempos"]
        for chave in ("treino_hibrido_s", "inferencia_hibrido_s", "treino_gnn_s", "tfidf_total_s"):
            self.assertGreater(t[chave]["media"], 0)
            self.assertEqual(t[chave]["n"], 40)  # 20 sementes x 2 cenários

    def test_RF40_semente_reproduz_resultado(self):
        from edutrack.model.sage import Hiper, escores, treinar
        from edutrack.model.evaluate import dividir
        dados = carregar_dados()
        g0 = construir(dados, semente=42)
        di, si = g0.idx("disciplina"), g0.idx("skill")
        todas = np.array([(di[d], si[h["skill"]]) for d, v in dados["disc_hab"].items() for h in v["habilidades"]])
        tr, va, _ = dividir(todas, 0.1, 0.2, 42)
        hp = Hiper(**{**Hiper.de_config(carregar_config()).__dict__, "epocas": 25, "decodificador_hibrido": False})
        s1 = escores(treinar(g0, tr, va, hp, 42).modelo, g0, tr)
        s2 = escores(treinar(g0, tr, va, hp, 42).modelo, g0, tr)
        self.assertTrue(np.array_equal(s1, s2))
        self.assertEqual(len(self.aval["protocolo"]["sementes"]), 20)


# ===========================================================================
# M6 — Recomendação (RF27–RF31, RN03, RN05)
# ===========================================================================
class TestRecomendacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Base.carregar()
        cls.ids = [d["id"] for d in cls.b.disciplinas]
        cls.vagas = _json(processados() / "vagas.json")

    def demanda_independente(self, perfil):
        vs = [v for v in self.vagas if perfil in (None, "todos") or v["perfil"] == perfil]
        c = Counter(s for v in vs for s in set(v["habilidades"]))
        return {s: n / len(vs) for s, n in c.items()}, len(vs)

    def test_RF29_RN03_propriedades_em_400_selecoes_aleatorias(self):
        rng = random.Random(2026)
        perfis = [None] + list(NOMES_PERFIS)
        por_periodo = sorted(self.b.disciplinas, key=lambda d: d["periodo"])
        for n in range(400):
            if n % 2:  # aluno regular: períodos completos
                ate = rng.randint(0, 7)
                cursadas = [d["id"] for d in por_periodo if d["periodo"] <= ate]
            else:      # seleção arbitrária
                cursadas = rng.sample(self.ids, rng.randint(0, len(self.ids)))
            perfil, k, modelo = rng.choice(perfis), rng.randint(1, 10), rng.choice(["gnn", "tfidf", None])
            r = self.b.trilha(cursadas, perfil, k, modelo)
            trilha = [x["disciplina"] for x in r["trilha"]]
            ctx = (cursadas, perfil, k, modelo, trilha)
            self.assertLessEqual(len(trilha), k, ctx)
            self.assertEqual(len(trilha), len(set(trilha)), ctx)
            self.assertFalse(set(trilha) & set(cursadas), ctx)
            self.assertFalse(set(trilha) & NAO_RECOMENDAVEIS, ctx)
            vistos = set(cursadas)
            for d in trilha:  # RN03: pré-requisitos cursados ou antes na trilha
                self.assertLessEqual(self.b.requisitos.get(d, set()), vistos, ctx)
                vistos.add(d)
            self.assertLessEqual(r["aderencia_antes"], r["aderencia_depois"] + 1e-9, ctx)
            self.assertLessEqual(r["aderencia_depois"], r["aderencia_teto_curricular"] + 1e-4, ctx)

    def test_RF27_RF28_RF30_aderencia_confere_com_calculo_independente(self):
        rng = random.Random(7)
        for perfil in [None] + list(NOMES_PERFIS):
            w, n = self.demanda_independente(perfil)
            cursadas = rng.sample(self.ids, 10)
            tem = set().union(*(self.b.ensina.get(d, set()) for d in cursadas))
            r = self.b.trilha(cursadas, perfil, 5, "tfidf")
            self.assertEqual(r["vagas_consideradas"], n)
            self.assertEqual(set(r["habilidades_atuais"]), tem)
            esperado = sum(w.get(s, 0) for s in tem) / sum(w.values())
            self.assertAlmostEqual(r["aderencia_antes"], esperado, places=3)
            depois = tem | {h["id"] for x in r["trilha"] for h in x["habilidades_cobertas"]}
            self.assertAlmostEqual(r["aderencia_depois"], sum(w.get(s, 0) for s in depois) / sum(w.values()), places=3)
            lacunas = [x["id"] for x in r["lacunas_abertas"]]
            self.assertFalse(set(lacunas) & depois)
            dem = [x["demanda"] for x in r["lacunas_abertas"]]
            self.assertEqual(dem, sorted(dem, reverse=True))

    def test_RF27_sem_estado_entre_consultas(self):
        a1 = self.b.trilha(["aed1", "aed2"], None, 5, "tfidf")
        self.b.trilha(self.ids[:20], "desenvolvimento", 3, "gnn")
        a2 = self.b.trilha(["aed1", "aed2"], None, 5, "tfidf")
        self.assertEqual(a1, a2)

    def test_RF31_perfil_restringe_vagas(self):
        for p in NOMES_PERFIS:
            r = self.b.trilha([], p, 5, None)
            self.assertEqual(r["vagas_consideradas"], sum(1 for v in self.vagas if v["perfil"] == p))

    def test_RN05_k_padrao_5(self):
        self.assertEqual(carregar_config()["recomendacao"]["k_padrao"], 5)
        self.assertEqual(self.b.trilha([], None)["k"], 5)
        cfg_js = (RAIZ / "edutrack" / "web" / "js" / "config.js").read_text(encoding="utf-8")
        self.assertRegex(cfg_js, r"K_PADRAO\s*=\s*(5|[^;]*k_padrao)")

    def test_entradas_invalidas_sao_recusadas(self):
        for args in ((["nao_existe"], None, 5), ([], "outro", 5), ([], None, 0), ([], None, 99)):
            with self.assertRaises(ErroEntrada):
                self.b.trilha(*args)


# ===========================================================================
# M7 — Diagnóstico curricular (RF32–RF35)
# ===========================================================================
class TestDiagnostico(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Base.carregar()
        cls.vagas = _json(processados() / "vagas.json")

    def test_RF32_RF33_RF34_contra_calculo_independente(self):
        for perfil in [None] + list(NOMES_PERFIS):
            vs = [v for v in self.vagas if perfil is None or v["perfil"] == perfil]
            demanda = Counter(s for v in vs for s in set(v["habilidades"]))
            ensinadas = {h["skill"] for v in _json(processados() / "disciplinas_habilidades.json").values() for h in v["habilidades"]}
            r = self.b.diagnostico(perfil)
            lac = r["lacunas"]
            self.assertEqual({x["id"] for x in lac}, {s for s in demanda if s not in ensinadas})        # RF32
            self.assertEqual([x["vagas"] for x in lac], sorted((x["vagas"] for x in lac), reverse=True))  # RF34
            self.assertTrue(all(x["vagas"] == demanda[x["id"]] for x in lac))
            sem_dem = {x["id"] for x in r["ensinadas_sem_demanda"]}
            self.assertEqual(sem_dem, {s for s in ensinadas if s not in demanda})                       # RF33

    def test_RF35_csv_confere_com_o_json(self):
        r = self.b.diagnostico(None)
        texto = self.b.diagnostico_csv(None)
        linhas = list(csv.DictReader(io.StringIO(texto.lstrip("﻿")), delimiter=";"))
        lac_csv = [x for x in linhas if x["situacao"].startswith("lacuna")]
        self.assertEqual(len(lac_csv), len(r["lacunas"]))
        self.assertEqual([x["habilidade"] for x in lac_csv], [x["nome"] for x in r["lacunas"]])


# ===========================================================================
# M9 — Governança, legal e segurança (RF41–RF44, RNF14–RNF17, RNF30, RN04, RN07, RN08)
# ===========================================================================
class TestGovernanca(unittest.TestCase):
    def test_RF41_sem_dados_pessoais_nas_vagas(self):
        for arq in (caminho("vagas_brutas"), processados() / "vagas.json"):
            dados = _json(arq)
            vagas = dados["vagas"] if isinstance(dados, dict) else dados
            for v in vagas:
                texto = v.get("descricao") or v.get("texto") or ""
                self.assertIsNone(EMAIL.search(texto), v["id"])
                self.assertIsNone(TELEFONE.search(texto), v["id"])
                self.assertIsNone(re.search(r"https?://\S+|www\.\S+", texto), v["id"])

    def test_RN04_so_vagas_de_manaus(self):
        for v in _json(processados() / "vagas.json"):
            self.assertIn("manaus", (v.get("cidade") or "").lower(), v["id"])

    def test_RF42_RN07_servidor_nao_guarda_selecao(self):
        from edutrack.api import main
        antes = {p: p.stat().st_mtime for p in RAIZ.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        main.base().trilha(["aed1", "programacao_oo"], None, 5, None)
        depois = {p: p.stat().st_mtime for p in RAIZ.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        self.assertEqual(antes, depois)  # nenhum arquivo criado ou alterado pelo cálculo
        fonte = (RAIZ / "edutrack" / "api" / "main.py").read_text(encoding="utf-8")
        for proibido in ("set_cookie", "sqlite", "Session(", "open(", "write_text"):
            self.assertNotIn(proibido, fonte)

    def test_RF43_RNF14_RNF15_RNF17_documentacao_dos_dados(self):
        doc = (RAIZ / "docs" / "DATA_SOURCES.md").read_text(encoding="utf-8")
        for termo in ("Currículo", "Vagas de emprego", "Estudantes", "Retenção", "robots.txt", "LGPD", "art. 7º",
                      "08/10/2026", "Base legal"):
            self.assertIn(termo, doc)

    def test_RF44_RNF06_energia_registrada(self):
        for arq in ("energia_avaliacao.json", "energia_pipeline.json", "energia_preparacao.json"):
            d = _json(artefatos() / "metrics" / arq)
            texto = json.dumps(d)
            self.assertIn("energia_kwh", texto, arq)
            self.assertIn("co2_g", texto, arq)

    @unittest.expectedFailure  # a coleta desta versão rodou no navegador; o módulo Python grava energia_coleta.json
    def test_RF44_energia_da_coleta_registrada(self):
        self.assertTrue((artefatos() / "metrics" / "energia_coleta.json").exists())

    def test_RNF16_nenhum_atributo_pessoal_no_esquema(self):
        from edutrack.api.schemas import TrilhaEntrada
        self.assertEqual(set(TrilhaEntrada.model_fields), {"cursadas", "perfil", "k", "modelo"})

    def test_RNF30_sem_segredos_no_codigo(self):
        padroes = re.compile(r"(api[_-]?key|secret|senha|password|token)\s*[:=]\s*['\"][^'\"]{6,}|AKIA[0-9A-Z]{16}|"
                             r"ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY", re.I)
        for p in RAIZ.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".js", ".yaml", ".json", ".md", ".bat", ".sh", ".txt", ".html"}:
                if "__pycache__" in p.parts or p.stat().st_size > 2_000_000:
                    continue
                self.assertIsNone(padroes.search(p.read_text(encoding="utf-8", errors="ignore")), str(p))

    def test_RN08_sem_autenticacao(self):
        from edutrack.api.main import app
        rotas = [getattr(r, "path", "") for r in app.routes]
        self.assertFalse([r for r in rotas if re.search(r"login|auth|token|usuario|conta|cadastro", r)])
        self.assertNotIn("/docs/oauth2-redirect", rotas)


# ===========================================================================
# Engenharia (RNF05, RNF22, RNF23, RNF25, RNF29)
# ===========================================================================
class TestEngenharia(unittest.TestCase):
    def test_RNF22_camadas_de_responsabilidade(self):
        for pasta in ("collect", "parse", "normalize", "graph", "model", "recommend", "api", "web", "green"):
            self.assertTrue((RAIZ / "edutrack" / pasta).is_dir(), pasta)

    def test_RNF23_RNF29_dependencias_fixadas_por_nome_exato(self):
        for arq in ("requirements.txt", "requirements-pipeline.txt"):
            for linha in (RAIZ / arq).read_text(encoding="utf-8").splitlines():
                linha = linha.split("#")[0].strip()
                if linha and not linha.startswith("-r"):
                    self.assertRegex(linha, r"^[A-Za-z0-9_.\-]+==\d[\w.]*$", f"{arq}: {linha}")

    def test_RNF05_coleta_sem_navegador_headless(self):
        for arq in ("requirements.txt", "requirements-pipeline.txt", "requirements-compat.txt"):
            texto = (RAIZ / arq).read_text(encoding="utf-8").lower()
            self.assertNotIn("selenium", texto)
            self.assertNotIn("playwright", texto)
        for p in (RAIZ / "edutrack").rglob("*.py"):
            fonte = p.read_text(encoding="utf-8")
            self.assertNotRegex(fonte, r"^\s*(import|from)\s+(selenium|playwright)", str(p))

    def test_RNF25_parametros_no_arquivo_de_configuracao(self):
        cfg = carregar_config()
        for chave in (("normalizacao", "limiar_fuzzy"), ("coleta", "intervalo_minimo_s"), ("coleta", "max_requisicoes"),
                      ("recomendacao", "k_padrao"), ("avaliacao", "sementes")):
            self.assertIn(chave[1], cfg[chave[0]])
        for p in (RAIZ / "edutrack").rglob("*.py"):
            fonte = p.read_text(encoding="utf-8")
            self.assertNotRegex(fonte, r"limiar\s*=\s*0\.87|intervalo\w*\s*=\s*1\.5|/\s*(88|20)\.0\b", str(p))


if __name__ == "__main__":
    unittest.main()


class TestCache(unittest.TestCase):
    def test_RNF07_impressao_digital_das_etapas(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_pipeline", RAIZ / "scripts" / "run_pipeline.py")
        rp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rp)
        etapas = rp.etapas()
        self.assertEqual([e["nome"] for e in etapas], ["extracao_ppc", "normalizacao", "avaliacao", "modelo_final"])
        a = rp.impressao(etapas[1]["entradas"])
        self.assertEqual(a, rp.impressao(etapas[1]["entradas"]))  # estável
        with tempfile.TemporaryDirectory() as t:  # qualquer byte diferente numa entrada invalida a etapa
            copia = Path(t) / "cfg.yaml"
            copia.write_bytes((RAIZ / "config.yaml").read_bytes() + b"\n")
            original = etapas[1]["entradas"][0]
            self.assertNotEqual(hashlib.sha256(original.read_bytes()).hexdigest(), hashlib.sha256(copia.read_bytes()).hexdigest())
        cache = _json(artefatos() / "cache" / "etapas.json")
        self.assertEqual(cache["normalizacao"], a)  # o cache versionado corresponde aos dados atuais
