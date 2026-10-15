"""Coleta de vagas públicas de TI em Manaus no portal Talent.com (RF01–RF06, RF41, RF43).

Respeita o robots.txt antes de cada requisição (RF02), identifica-se por
User-Agent descritivo e espera um intervalo mínimo entre requisições (RF03),
limita o total de requisições por execução (RNF08), não usa navegador headless
(RNF05) e segue em frente quando uma página falha (RNF20). Cada vaga é gravada
com título, descrição, localidade, data de publicação, data de coleta e URL de
origem (RF04); e-mails, telefones e links são removidos já na ingestão (RF41).
Duplicatas por identificador/URL são descartadas aqui; duplicatas pelo par
(título, empresa) são tratadas na normalização (RF05).

O conjunto de dados desta versão (data/raw/vagas_talent_manaus.json) foi coletado
em 08/10/2026 pela rotina equivalente em JavaScript de scripts/coleta_navegador.js,
com os mesmos termos, intervalo e regras, porque o ambiente de construção não tinha
acesso direto ao portal. Este módulo reproduz a coleta a partir de qualquer computador.

Uso:  python -m edutrack.collect.scrape_talent [--saida data/raw/vagas_talent_manaus.json] [--max-paginas 3]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
import unicodedata
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from edutrack.config import RAIZ, carregar_config
from edutrack.green.energy import RastreadorEnergia, registrar

log = logging.getLogger("edutrack.coleta")

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_TELEFONE = re.compile(r"(\+?55[\s.-]?)?\(?\b\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}\b")
_LINK = re.compile(r"https?://\S+|www\.\S+")
TITULO_TI = re.compile(
    r"(desenvolv|program|software|sistema|\bti\b|t\.i\.|tecnologia|dados|\bdata\b|suporte|\brede|infraestrutura|devops|"
    r"cloud|nuvem|seguranca da informacao|ciberseg|cyber|full ?stack|front|back.?end|mobile|android|\bios\b|\bweb\b|java|"
    r"python|\.net|c#|\bsap\b|\berp\b|totvs|protheus|\bbi\b|power ?bi|analytics|\bqa\b|teste|automac|robotic|\bplc\b|"
    r"\bclp\b|embarcad|firmware|hardware|help ?desk|service ?desk|\bn[123]\b|nivel [123]|\bdba\b|banco de dados|"
    r"inteligencia artificial|machine learning|\bia\b|\bml\b|\bux\b|\bui\b|scrum|product owner|governanca de ti|telecom|"
    r"\bsre\b|computac|informatica|iot|arquitet|cientista|engenharia de dados|tecnico de campo|helpdesk|\bnoc\b|\bsoc\b|"
    r"ciencia de dados|digital|tech|fibra|servidor|eletronic|testador)"
)


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c)).lower()


def limpar(texto: str) -> str:
    """RF41 — remove dados pessoais e normaliza espaços."""
    texto = _EMAIL.sub("[email removido]", texto or "")
    texto = _TELEFONE.sub("[telefone removido]", texto)
    texto = _LINK.sub("[link removido]", texto)
    texto = re.sub(r"[ \t ]+", " ", texto)
    return re.sub(r"\n\s*\n+", "\n", texto).strip()


def _texto_html(html: str) -> str:
    from bs4 import BeautifulSoup

    html = re.sub(r"<(br|/p|/li|/h[1-6]|/div|/ul|/ol)[^>]*>", lambda m: m.group(0) + "\n", html or "", flags=re.I)
    return BeautifulSoup(html, "html.parser").get_text()


def ids_da_busca(html: str) -> list[tuple[str, str]]:
    """Pares (id, título) dos cartões de vaga de uma página de busca."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select('[data-testid^="jobcard-container-"]'):
        i = card["data-testid"].rsplit("-", 1)[-1]
        t = card.select_one('h2, h3, [class*="title"], [class*="Title"]')
        out.append((i, t.get_text(strip=True) if t else ""))
    if not out:
        out = [(i, "") for i in re.findall(r"/view\?id=(\d+)", html)]
    vistos, unicos = set(), []
    for i, t in out:
        if i not in vistos:
            vistos.add(i)
            unicos.append((i, t))
    return unicos


def tem_proxima_pagina(html: str, pagina: int) -> bool:
    return f"&amp;p={pagina + 1}" in html or f"&p={pagina + 1}" in html


def parse_vaga(html: str, id_vaga: str) -> dict | None:
    """Extrai a vaga do JSON-LD (JobPosting) ou, na falta dele, do corpo da página."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    jp = None
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            obj = json.loads(s.string or "")
        except json.JSONDecodeError:
            continue
        for g in obj.get("@graph", [obj]) if isinstance(obj, dict) else []:
            if isinstance(g, dict) and g.get("@type") == "JobPosting":
                jp = g
    base = {"id": id_vaga, "url": f"https://br.talent.com/view?id={id_vaga}",
            "data_coleta": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if jp:
        end = (jp.get("jobLocation") or {}).get("address") or {}
        return {**base, "titulo": jp.get("title", ""), "empresa": (jp.get("hiringOrganization") or {}).get("name", ""),
                "cidade": end.get("addressLocality", ""), "regiao": end.get("addressRegion", ""),
                "data_publicacao": jp.get("datePosted", ""), "tipo_contrato": jp.get("employmentType", ""),
                "categoria_ocupacional": jp.get("occupationalCategory", ""), "industria": jp.get("industry", ""),
                "descricao": limpar(_texto_html(jp.get("description", ""))), "extracao": "json-ld"}
    rotulo = soup.find(lambda t: t.name in ("span", "div", "p", "h2", "h3") and t.get_text(strip=True) == "Descrição da vaga")
    if not rotulo:
        return None
    corpo = rotulo.find_next_sibling() or (rotulo.parent.find_next_sibling() if rotulo.parent else None)
    if not corpo:
        return None
    h1 = soup.find("h1")
    cab = [t.get_text(strip=True) for t in (h1.parent.parent.find_all(["span", "div", "p"]) if h1 and h1.parent and h1.parent.parent else [])
           if not t.find(["span", "div", "p"])]
    empresa = local = ""
    if "•" in cab:
        k = cab.index("•")
        empresa, local = (cab[k - 1] if k else ""), (cab[k + 1] if k + 1 < len(cab) else "")
    return {**base, "titulo": h1.get_text(strip=True) if h1 else "", "empresa": empresa, "cidade": local.split(",")[0].strip(),
            "regiao": local, "data_publicacao": "", "data_publicacao_relativa": next((c for c in cab if c.startswith("Há ")), ""),
            "tipo_contrato": "", "categoria_ocupacional": "", "industria": "",
            "descricao": limpar(_texto_html(str(corpo))), "extracao": "dom"}


class Coletor:
    def __init__(self, cfg: dict):
        import requests

        self.c = cfg["coleta"]
        self.sessao = requests.Session()
        self.sessao.headers["User-Agent"] = self.c["user_agent"]
        self.sessao.headers["Accept-Language"] = "pt-BR,pt;q=0.9"
        self.requisicoes = 0
        self.falhas: list[tuple[str, str]] = []
        self.descartadas = 0
        self._ultima = 0.0
        self.robots = urllib.robotparser.RobotFileParser(urljoin(self.c["dominio"], "/robots.txt"))
        try:
            self.robots.read()  # RF02
        except Exception as exc:  # RNF20: sem robots.txt conferido, nada é coletado (postura conservadora)
            self.robots.disallow_all = True
            self.falhas.append((self.robots.url, f"robots.txt inacessível: {type(exc).__name__}"))
            log.warning("não foi possível ler %s (%s) — coleta abortada", self.robots.url, exc)

    def obter(self, caminho: str) -> str | None:
        url = urljoin(self.c["dominio"], caminho)
        if not self.robots.can_fetch(self.c["user_agent"], url):
            self.falhas.append((url, "bloqueado pelo robots.txt"))
            log.warning("robots.txt não autoriza %s — abortado", url)
            return None
        if self.requisicoes >= self.c["max_requisicoes"]:
            raise RuntimeError("teto de requisições atingido (RNF08)")
        espera = self.c["intervalo_minimo_s"] - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)  # RF03
        self._ultima = time.monotonic()
        self.requisicoes += 1
        try:
            r = self.sessao.get(url, timeout=self.c["timeout_s"])
            if r.status_code != 200:
                self.falhas.append((url, f"HTTP {r.status_code}"))
                return None
            return r.text
        except Exception as exc:  # RNF20: registra e segue
            self.falhas.append((url, type(exc).__name__))
            return None

    def coletar(self, max_paginas: int) -> dict:
        inicio = datetime.now(timezone.utc).isoformat(timespec="seconds")
        titulos: dict[str, dict] = {}
        buscas = []
        vagas: list[dict] = []
        local = quote_plus(self.c["localidade"])
        try:
            for termo in self.c["termos_busca"]:
                for p in range(1, max_paginas + 1):
                    html = self.obter(f"/jobs?k={quote_plus(termo)}&l={local}" + (f"&p={p}" if p > 1 else ""))
                    if html is None:
                        break
                    ids = ids_da_busca(html)
                    buscas.append([termo, p, len(ids)])
                    for i, titulo in ids:
                        titulos.setdefault(i, {"titulo": titulo, "termos": []})["termos"].append(termo)
                    if not ids or not tem_proxima_pagina(html, p):
                        break
            for i, info in titulos.items():
                if info["titulo"] and not TITULO_TI.search(sem_acento(info["titulo"])):
                    self.descartadas += 1  # título fora de TI (RF06)
                    continue
                html = self.obter(f"/view?id={i}")
                v = parse_vaga(html, i) if html else None
                if v is None:
                    self.falhas.append((i, "página sem descrição"))
                    continue
                v["termos_busca"] = info["termos"]
                vagas.append(v)
        except RuntimeError as exc:
            log.warning("%s", exc)
        meta = {
            "fonte": "br.talent.com", "rota": "/jobs e /view (permitidas pelo robots.txt)", "localidade": self.c["localidade"],
            "inicio_coleta": inicio, "fim_coleta": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "requisicoes_http": self.requisicoes, "intervalo_entre_requisicoes_s": self.c["intervalo_minimo_s"],
            "ids_listados": len(titulos), "vagas_coletadas": len(vagas), "descartadas_titulo": self.descartadas, "buscas": buscas,
            "falhas": len(self.falhas), "user_agent": self.c["user_agent"],
        }
        log.info("coletadas=%d listadas=%d descartadas=%d falhas=%d requisições=%d",  # RF06
                 len(vagas), len(titulos), self.descartadas, len(self.falhas), self.requisicoes)
        return {"meta": meta, "vagas": sorted(vagas, key=lambda v: v["id"])}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = carregar_config()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--saida", default=str(RAIZ / cfg["caminhos"]["vagas_brutas"]))
    ap.add_argument("--max-paginas", type=int, default=cfg["coleta"]["paginas_por_termo"])
    a = ap.parse_args()
    with RastreadorEnergia("coleta_de_vagas") as r:
        dados = Coletor(cfg).coletar(a.max_paginas)
    registrar([r.medicao], "energia_coleta.json")
    Path(a.saida).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{dados['meta']['vagas_coletadas']} vagas gravadas em {a.saida}")


if __name__ == "__main__":
    main()
