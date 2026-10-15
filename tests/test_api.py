"""API de ponta a ponta: sobe o uvicorn numa thread e chama as rotas por HTTP."""
import json
import socket
import threading
import time
import unittest
import re
import urllib.error
import urllib.parse
import urllib.request

import uvicorn

from edutrack.api.main import app


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.porta = porta_livre()
        cls.servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=cls.porta, log_level="warning"))
        cls.thread = threading.Thread(target=cls.servidor.run, daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.servidor.started:
                break
            time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.should_exit = True
        cls.thread.join(timeout=5)

    def req(self, caminho, corpo=None):
        url = f"http://127.0.0.1:{self.porta}{caminho}"
        dados = json.dumps(corpo).encode() if corpo is not None else None
        r = urllib.request.Request(url, data=dados, headers={"Content-Type": "application/json"} if dados else {})
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_pagina_principal_e_docs(self):
        st, h, corpo = self.req("/")
        self.assertEqual(st, 200)
        self.assertIn(b"<title>EduTrack", corpo)
        self.assertIn(b'src="js/app.js"', corpo)
        tipos = {"/js/app.js": "text/javascript", "/js/dados.js": "text/javascript", "/js/servico.js": "text/javascript",
                 "/css/style.css": "text/css", "/css/fonts.css": "text/css", "/fonts/Inter-Regular.woff": "font/woff",
                 "/assets/logo-et.svg": "image/svg+xml"}
        for recurso, tipo in tipos.items():  # módulos ES exigem tipo JavaScript, ainda mais com nosniff
            st, h, _ = self.req(recurso)
            self.assertEqual(st, 200, recurso)
            self.assertTrue(h["Content-Type"].startswith(tipo), (recurso, h["Content-Type"]))
        self.assertEqual(self.req("/docs")[0], 200)

    def test_sem_requisicoes_a_terceiros(self):  # LGPD e Green Software: a página só fala com o próprio serviço
        st, h, corpo = self.req("/")
        csp = h["Content-Security-Policy"]
        for diretiva in ("default-src 'self'", "script-src 'self'", "font-src 'self'", "connect-src 'self'", "frame-ancestors 'none'"):
            self.assertIn(diretiva, csp)
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertIsNone(re.search(rb"(src|href)=\"https?://", corpo))
        self.assertNotIn(b"googleapis", self.req("/css/fonts.css")[2])

    def test_pacote_da_interface(self):  # dados que a página carrega uma vez, coerentes entre si
        st, h, corpo = self.req("/api/interface")
        self.assertEqual(st, 200)
        p = json.loads(corpo)
        nomes = {x["n"] for x in p["habilidades"]}
        ids = {d["cod"] for d in p["disciplinas"]}
        self.assertEqual(len(ids), p["ppc"]["disciplinas_identificadas"])
        self.assertEqual(len(p["vagas"]), p["coleta"]["vagas_aceitas"])
        for d in p["disciplinas"]:
            self.assertLessEqual(set(d["skills"]), nomes, d["cod"])
        for d, reqs in p["prereq"].items():
            self.assertIn(d, ids)
            self.assertLessEqual(set(reqs), ids)
        for v in p["vagas"]:
            self.assertLessEqual(set(v["skills"]), nomes, v["id"])
            self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.\w+", json.dumps(v, ensure_ascii=False)))  # sem e-mails
        for hab, d in p["sugestoes"].items():
            self.assertIn(hab, nomes)
            self.assertIn(d, ids)
        self.assertIn(p["modelo"]["padrao"], ("tfidf", "gnn"))
        self.assertIn("texto_mascarado", p["metricas"]["cenarios"])

    def test_normalizacao_ao_vivo(self):  # RF11–RF13 pela mesma rotina do pipeline
        casos = {"linguagem python 3": ("exata", "Python"), "SpringBoot": ("aproximada", "Spring Boot"),
                 "Formação": ("nao_resolvido", None)}
        for termo, (camada, nome) in casos.items():
            st, h, corpo = self.req("/api/normalizar?termo=" + urllib.parse.quote(termo))
            self.assertEqual(st, 200, termo)
            r = json.loads(corpo)
            self.assertEqual(r["camada"], camada, termo)
            self.assertEqual(r["habilidade"]["nome"] if r["habilidade"] else None, nome, termo)
        self.assertEqual(self.req("/api/normalizar?termo=x&limiar=0.2")[0], 422)
        self.assertEqual(self.req("/api/normalizar")[0], 422)

    def test_auditoria_e_ontologia(self):  # RF14 e RF15
        st, h, corpo = self.req("/api/normalizacao/auditoria?camada=aproximada&tamanho=5")
        self.assertEqual(st, 200)
        a = json.loads(corpo)
        self.assertEqual(a["total"], a["por_camada"]["aproximada"])
        self.assertTrue(all(i["camada"] == "aproximada" and i["escore"] >= a["limiar"] for i in a["itens"]))
        self.assertEqual(self.req("/api/normalizacao/auditoria?camada=outra")[0], 422)
        o = json.loads(self.req("/api/ontologia")[2])
        self.assertEqual(len(o["habilidades"]), len(json.loads(self.req("/api/interface")[2])["habilidades"]))

    def test_rotas_de_leitura(self):
        for rota in ("/api/saude", "/api/disciplinas", "/api/habilidades", "/api/perfis", "/api/mercado",
                     "/api/diagnostico?perfil=dados_ia", "/api/metricas", "/api/sobre",
                     "/api/afinidade?habilidades=sql,cloud", "/api/grafo/subgrafo?tipo=skill&id=sql"):
            st, h, corpo = self.req(rota)
            self.assertEqual(st, 200, rota)
            json.loads(corpo)

    def test_trilha_e_tempo_de_resposta(self):  # RNF02: p95 <= 3 s em 30 execuções
        tempos = []
        for _ in range(30):
            t0 = time.perf_counter()
            st, h, corpo = self.req("/api/trilha", {"cursadas": ["aed1", "aed2", "programacao_oo"], "perfil": "todos", "k": 5})
            tempos.append(time.perf_counter() - t0)
            self.assertEqual(st, 200)
        tempos.sort()
        self.assertLessEqual(tempos[int(0.95 * len(tempos)) - 1], 3.0)
        r = json.loads(corpo)
        self.assertEqual(len(r["trilha"]), 5)
        self.assertEqual(h["Cache-Control"], "no-store")

    def test_validacao_de_entrada(self):
        self.assertEqual(self.req("/api/trilha", {"cursadas": ["xyz"]})[0], 422)
        self.assertEqual(self.req("/api/trilha", {"cursadas": [], "k": 99})[0], 422)
        self.assertEqual(self.req("/api/trilha", {"cursadas": [], "perfil": "outro"})[0], 422)
        self.assertEqual(self.req("/api/grafo/subgrafo?tipo=skill&id=nao_existe")[0], 404)

    def test_csv_do_diagnostico(self):  # RF35
        st, h, corpo = self.req("/api/diagnostico.csv")
        self.assertEqual(st, 200)
        self.assertIn("attachment", h["Content-Disposition"])
        self.assertTrue(corpo.decode("utf-8").startswith("﻿situacao;"))

    def test_sem_rotas_de_escrita(self):  # RNF31
        metodos = {m for r in app.routes for m in getattr(r, "methods", set())}
        self.assertFalse(metodos & {"PUT", "PATCH", "DELETE"})
        posts = [r.path for r in app.routes if "POST" in getattr(r, "methods", set())]
        self.assertEqual(posts, ["/api/trilha"])  # cálculo sem persistência


if __name__ == "__main__":
    unittest.main()
