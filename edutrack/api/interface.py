"""Dados agregados para a interface web (eT), lidos dos artefatos do pipeline.

Tudo aqui é leitura: o pacote é montado uma vez a partir de data/processed e
artifacts/ e servido pela rota GET /api/interface. Nenhum dado de estudante
passa por este módulo (RF42).
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from functools import lru_cache

from edutrack.config import artefatos, caminho, carregar_config, processados
from edutrack.core.texto import titulo_pt
from edutrack.normalize.normalize_skills import Normalizador
from edutrack.recommend.engine import NAO_RECOMENDAVEIS, NOMES_PERFIS, Base

# Modelos da avaliação experimental: chave usada pela interface -> nome em avaliacao.json
MODELOS_AVALIADOS = {
    "tfidf": "TF-IDF (cosseno)",
    "gnn": "GraphSAGE + texto (híbrido)",
    "gnn_pura": "GraphSAGE (GNN)",
    "gnn_l0": "GNN sem mensagens (L=0)",
    "coocorrencia": "Coocorrência (heurística)",
    "popularidade": "Popularidade",
}
NOMES_CURTOS = {"tfidf": "TF-IDF", "gnn": "GNN híbrida (GraphSAGE)", "gnn_pura": "GNN pura (GraphSAGE)",
                "gnn_l0": "GNN sem troca de mensagens", "coocorrencia": "Coocorrência", "popularidade": "Popularidade"}

# Nível da vaga: só o que o título declara (nada é inferido do texto)
_NIVEIS = [
    ("Estágio", re.compile(r"\best[aá]gi|\bestagi[aá]ri")),
    ("Júnior", re.compile(r"\b(jr|j[uú]nior)\b")),
    ("Pleno", re.compile(r"\b(pl|pleno)\b")),
    ("Sênior", re.compile(r"\b(sr|s[eê]nior)\b")),
]
_MODALIDADES = [("Híbrido", re.compile(r"h[ií]brid")), ("Remoto", re.compile(r"\bremot[oe]\b|\bremote\b")),
                ("Presencial", re.compile(r"\bpresencial\b"))]
_SIGLAS = {"TI", "T.I", "SR", "JR", "PL", "PCD", "SAP", "ERP", "QA", "QAPL", "IA", "BI", "SW", "N1", "N2", "N3", "AM",
           "CNC", "TOTVS", "PMO", "SGI", "PCP", "RH", "UX", "UI", "API", "AWS", "SQL", "NIL", "CP", "FOTA", "FUS",
           "SITA", "MES", "TIC", "P/205", "CLT", "PJ", "MOBILE", "PAY"}


def _json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cargo_legivel(titulo: str) -> str:
    """Título da vaga como publicado; só os escritos inteiramente em maiúsculas
    passam para caixa de título, preservando as siglas."""
    t = re.sub(r"\s+", " ", titulo or "").strip()
    letras = [c for c in t if c.isalpha()]
    if not letras or not all(c.isupper() for c in letras):
        return t
    out = re.sub(r"\((\w)", lambda m: "(" + m.group(1).upper(), titulo_pt(t))
    return re.sub(r"[A-Za-zÀ-ú0-9./]+", lambda m: m.group(0).upper() if m.group(0).upper().strip(".") in _SIGLAS else m.group(0), out)


def empresa_legivel(nome: str) -> str:
    nome = re.sub(r"\s+", " ", nome or "").strip()
    return titulo_pt(nome) if nome and nome == nome.lower() else nome


def niveis_do_titulo(titulo: str) -> list[str]:
    t = (titulo or "").lower()
    if _NIVEIS[0][1].search(t):
        return ["Estágio"]
    return [n for n, rx in _NIVEIS[1:] if rx.search(t)]


def modalidade_do_titulo(titulo: str) -> str | None:
    t = (titulo or "").lower()
    return next((m for m, rx in _MODALIDADES if rx.search(t)), None)


def _data_iso(valor: str | None) -> str | None:
    return valor if valor and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor) else None


def _data_relativa(valor: str | None) -> str | None:
    """Quando o portal só informa a idade do anúncio ("Há 3 dias", "Há +30 dias"), relativa à data da coleta."""
    return valor.strip().lower() if valor and valor.strip().lower().startswith("há ") else None


def _metricas(aval: dict) -> dict:
    ag = aval.get("agregado", {})
    out = {}
    for cen in ("texto_mascarado", "texto_completo"):
        modelos = {}
        for chave, nome in MODELOS_AVALIADOS.items():
            m = ag.get(cen, {}).get(nome)
            if not m:
                continue
            modelos[chave] = {"nome": NOMES_CURTOS[chave], "nome_completo": nome,
                              **{k: {"media": round(v["media"], 4), "dp": round(v["dp"], 4)} for k, v in m.items()}}
        out[cen] = modelos
    w = aval.get("testes_wilcoxon", {})
    chave = "texto_mascarado | GraphSAGE + texto (híbrido) vs TF-IDF (cosseno) | R@5"
    return {
        "cenarios": out,
        "k": aval.get("protocolo", {}).get("k", [1, 3, 5, 10]),
        "sorteios": len(aval.get("protocolo", {}).get("sementes", [])),
        "arestas_ensina": aval.get("protocolo", {}).get("arestas_ensina"),
        "particao": aval.get("protocolo", {}).get("particao"),
        "wilcoxon_gnn_vs_tfidf_r5_latente": w.get(chave, {}).get("p_valor"),
        "tempos": aval.get("tempos", {}),
    }


def montar_pacote(b: Base) -> dict:
    cfg = carregar_config()
    cob = _json(processados() / "cobertura_ppc.json")
    resumo = _json(processados() / "resumo_normalizacao.json")
    aval = _json(artefatos() / "metrics" / "avaliacao.json")
    meta_vagas = _json(caminho("vagas_brutas")).get("meta", {})
    ont = json.loads(caminho("ontologia").read_text(encoding="utf-8"))

    cats = list(b.ont.categorias.keys())
    contagem = Counter(s for v in b.vagas for s in set(v["habilidades"]))

    habilidades = []
    for h in b.ont.habilidades.values():
        habilidades.append({"id": h.id, "n": h.nome, "cat": cats.index(h.categoria), "syn": list(h.aliases) + list(h.aliases_cs),
                            "vagas": contagem.get(h.id, 0)})

    def nomes_skills(ids):
        return sorted((b.nome_skill(s) for s in ids), key=lambda n: n.lower())

    disciplinas = []
    for d in sorted(b.disciplinas, key=lambda x: (x["periodo"], titulo_pt(x["nome"]))):
        disciplinas.append({
            "cod": d["id"], "nome": titulo_pt(d["nome"]), "periodo": d["periodo"], "ch": d.get("carga_horaria"),
            "codigo": d.get("codigo"), "creditos": d.get("creditos"), "ementa": d.get("ementa") or "",
            "fonte": d["fonte_ementa"], "recomendavel": d["id"] not in NAO_RECOMENDAVEIS,
            "skills": nomes_skills(b.ensina.get(d["id"], ())),
        })

    vagas = []
    for v in b.vagas:
        vagas.append({
            "id": v["id"], "cargo": cargo_legivel(v["titulo"]), "empresa": empresa_legivel(v["empresa"]),
            "niveis": niveis_do_titulo(v["titulo"]), "modalidade": modalidade_do_titulo(v["titulo"]),
            "cidade": "Manaus/AM", "perfil": v["perfil"], "perfil_nome": NOMES_PERFIS.get(v["perfil"], v["perfil"]),
            "url": v.get("url"), "publicada": _data_iso(v.get("data_publicacao")), "coletada": (v.get("data_coleta") or "")[:10],
            "publicada_relativa": _data_relativa(v.get("data_publicacao")),
            "skills": nomes_skills(set(v["habilidades"])),
        })

    sugestoes, sug_info = {}, {}
    for s in sorted(contagem, key=lambda x: -contagem[x]):
        if s in b.ensinadas:
            continue
        apoio = b.apoio_estrutural(s)
        if apoio:
            nome = b.nome_skill(s)
            sugestoes[nome] = apoio["disciplina"]
            sug_info[nome] = {"afinidade": apoio["afinidade"], "ponte": apoio["ponte"]}

    perfis = [{"id": "todos", "t": "Todas as vagas", "vagas": len(b.vagas)}] + [
        {"id": p, "t": n, "vagas": sum(1 for v in b.vagas if v["perfil"] == p)} for p, n in NOMES_PERFIS.items()]

    inicio = (meta_vagas.get("inicio_coleta") or "")[:10]
    return {
        "versao": cfg.get("versao"),
        "ppc": {
            "codigo": cfg["ppc"]["curriculo"], "instituicao": "FAMETRO",
            "periodos_processados": sorted({d["periodo"] for d in b.disciplinas}),
            "total_periodos": cfg["ppc"]["periodos_esperados"], "disciplinas_esperadas": cfg["ppc"]["disciplinas_esperadas"],
            "disciplinas_identificadas": cob.get("disciplinas_identificadas"), "com_programa_oficial": cob.get("com_programa_oficial"),
            "com_ementa_referencia": cob.get("com_ementa_referencia"), "declaracao": cob.get("declaracao_RNF21"),
        },
        "coleta": {
            "fonte": "Talent.com Brasil", "dominio": "br.talent.com", "filtro": cfg["coleta"]["localidade"].replace(", ", "/"),
            "data": inicio, "anuncios_listados": meta_vagas.get("ids_listados"), "vagas_coletadas": meta_vagas.get("vagas_coletadas"),
            "vagas_aceitas": len(b.vagas), "requisicoes": meta_vagas.get("requisicoes_http"),
            "intervalo_s": meta_vagas.get("intervalo_entre_requisicoes_s"),
        },
        "categorias": [b.ont.categorias[c] for c in cats],
        "habilidades": habilidades,
        "disciplinas": disciplinas,
        "prereq": {d: sorted(r) for d, r in b.requisitos.items()},
        "vagas": vagas,
        "sugestoes": sugestoes,
        "sugestoes_info": sug_info,
        "perfis": perfis,
        "modelo": {"padrao": b.meta_modelo.get("modelo_padrao", "tfidf"),
                   "motivo": b.meta_modelo.get("motivo_modelo_padrao", ""),
                   "nomes": {k: NOMES_CURTOS[k] for k in ("tfidf", "gnn")}},
        "metricas": _metricas(aval),
        "normalizacao": {
            "limiar": cfg["normalizacao"]["limiar_fuzzy"], "habilidades": resumo.get("habilidades_na_ontologia"),
            "categorias": resumo.get("categorias"), "sinonimos": resumo.get("sinonimos"), "decisoes": resumo.get("decisoes", {}),
            "cobertura": resumo.get("cobertura_RNF18_vagas", {}), "ontologia_versao": ont.get("versao"),
        },
        "quarentena": quarentena(),
        "recomendacao": {"k_padrao": cfg["recomendacao"]["k_padrao"], "k_maximo": cfg["recomendacao"]["k_maximo"]},
    }


@lru_cache(maxsize=1)
def quarentena(freq_minima: int = 2) -> list[dict]:
    """Termos não resolvidos com frequência >= freq_minima (RF15), com o
    sinônimo mais parecido pela razão de caracteres como sugestão de curadoria."""
    arq = processados() / "nao_resolvidos.csv"
    if not arq.exists():
        return []
    n = normalizador(carregar_config()["normalizacao"]["limiar_fuzzy"])
    mapa = n.ont.sinonimos()
    # termos com forma de tecnologia que contam para a cobertura do RNF18 (calculados no pipeline)
    tecnicos = set(_json(processados() / "resumo_normalizacao.json").get("cobertura_RNF18_vagas", {}).get("nao_resolvidos_elegiveis", []))
    out = []
    with open(arq, encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            freq = int(linha["frequencia"])
            if freq < freq_minima:
                continue
            termo = linha["termo"]
            prox = n.similaridade_bruta(termo, 1)
            cand = None
            if prox and prox[0][1] >= 0.75:  # abaixo disso a sugestão só atrapalharia a curadoria
                sin, esc = prox[0]
                cand = {"habilidade": n.ont.habilidades[mapa[sin]].nome, "sinonimo": sin, "escore": round(esc, 4)}
            out.append({"termo": termo, "n": freq, "tecnico": termo in tecnicos, "cand": cand})
    return out


@lru_cache(maxsize=8)
def normalizador(limiar: float) -> Normalizador:
    cfg = carregar_config()["normalizacao"]
    return Normalizador(_ontologia(), limiar=limiar, tamanho_minimo_fuzzy=cfg.get("tamanho_minimo_fuzzy", 5))


@lru_cache(maxsize=1)
def _ontologia():
    from edutrack.normalize.normalize_skills import Ontologia
    return Ontologia(caminho("ontologia"))


def testar_termo(termo: str, limiar: float) -> dict:
    """Aplica ao termo isolado as duas camadas da normalização (RF12–RF14)."""
    n = normalizador(round(float(limiar), 2))
    sid, camada, escore, alvo = n.normalizar_termo(termo)
    hab = None
    if sid:
        h = n.ont.habilidades[sid]
        hab = {"id": h.id, "nome": h.nome, "categoria": n.ont.categorias[h.categoria]}
    parecido = None
    if not sid:
        prox = n.similaridade_bruta(termo, 1)
        if prox:
            sin, esc = prox[0]
            h = n.ont.habilidades[n.ont.sinonimos()[sin]]
            parecido = {"sinonimo": sin, "habilidade": h.nome, "escore": round(esc, 4)}
    rotulo = {"exata": "exata", "fuzzy": "aproximada", "nao_resolvido": "nao_resolvido"}[camada]
    if camada == "exata":
        motivo = "o termo, sem acentos e sem distinção de maiúsculas, é um sinônimo cadastrado na ontologia"
    elif camada == "fuzzy" and escore >= 1.0:
        motivo = "a forma compacta do termo (sem espaços e pontuação) coincide com a de um sinônimo"
    elif camada == "fuzzy":
        motivo = "os termos de conteúdo se alinham um a um com os do sinônimo e a razão de caracteres atinge o limiar"
    elif len(termo.strip()) < n.tam_min and not hab:
        motivo = f"termos com menos de {n.tam_min} caracteres só valem na camada exata"
    elif escore:
        motivo = "a razão de caracteres ficou abaixo do limiar"
    else:
        motivo = "nenhum sinônimo se alinha termo a termo com o texto informado"
    return {"termo": termo, "limiar": round(float(limiar), 2), "camada": rotulo, "escore": round(float(escore), 4),
            "sinonimo": alvo or None, "habilidade": hab, "mais_parecido": parecido, "motivo": motivo}


@lru_cache(maxsize=1)
def _auditoria() -> list[dict]:
    arq = processados() / "auditoria_normalizacao.csv"
    if not arq.exists():
        return []
    b = Base.carregar()
    nomes_d = {d["id"]: titulo_pt(d["nome"]) for d in b.disciplinas}
    nomes_v = {v["id"]: cargo_legivel(v["titulo"]) for v in b.vagas}
    ont = _ontologia()
    out = []
    with open(arq, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tipo = r["tipo_documento"]
            doc = nomes_d.get(r["doc_id"]) if tipo == "disciplina" else nomes_v.get(r["doc_id"])
            sid = r["skill_id"] or None
            out.append({"origem": "Ementa" if tipo == "disciplina" else "Vaga", "documento": doc or r["doc_id"],
                        "termo": r["termo_original"], "habilidade": ont.habilidades[sid].nome if sid in ont.habilidades else None,
                        "camada": {"fuzzy": "aproximada"}.get(r["camada"], r["camada"]), "escore": float(r["escore"] or 0),
                        "sinonimo": r["sinonimo"] or None})
    return out


def auditoria(pagina: int, tamanho: int, camada: str | None, origem: str | None) -> dict:
    linhas = _auditoria()
    if camada and camada != "todas":
        linhas = [x for x in linhas if x["camada"] == camada]
    if origem and origem != "todas":
        linhas = [x for x in linhas if x["origem"].lower() == origem.lower()]
    total = len(linhas)
    paginas = max(1, -(-total // tamanho))
    pagina = min(max(1, pagina), paginas)
    contagem = Counter(x["camada"] for x in _auditoria())
    return {"total": total, "pagina": pagina, "paginas": paginas, "tamanho": tamanho,
            "limiar": carregar_config()["normalizacao"]["limiar_fuzzy"], "por_camada": dict(contagem),
            "itens": linhas[(pagina - 1) * tamanho: pagina * tamanho]}

