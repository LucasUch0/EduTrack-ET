"""Aplica a normalização semântica às ementas e às vagas e grava os artefatos
processados com trilha de auditoria (RF11–RF16, RF41, RN01, RN04, RNF18).

Saídas em data/processed/:
  disciplinas_habilidades.json   disciplina -> habilidades (com camada e escore)
  vagas.json                     vagas de TI de Manaus aceitas, com habilidades e perfil
  vagas_descartadas.json         vagas excluídas e o motivo (duplicada, não-TI, fora de Manaus)
  auditoria_normalizacao.csv     uma linha por decisão (termo original -> canônico)
  nao_resolvidos.csv             quarentena ordenada por frequência (RF15)
  resumo_normalizacao.json       contagens e cobertura (RNF18)

Uso:  python -m edutrack.normalize.pipeline
"""
from __future__ import annotations

import csv
import json
import logging
import re
import unicodedata
from collections import Counter, defaultdict

from edutrack.core.texto import titulo_pt
from edutrack.config import caminho, carregar_config, processados
from edutrack.normalize.normalize_skills import (
    Normalizador, Ontologia, cobertura, relatorio_nao_resolvidos, ocorrencias_para_linhas,
)

log = logging.getLogger("edutrack.normalizacao")

# --------------------------------------------------------------------------
# RF41 — remoção de dados pessoais que tenham escapado da coleta
# --------------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_TELEFONE = re.compile(r"(\+?55[\s.-]?)?\(?\b\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}\b")
_URL = re.compile(r"https?://\S+|www\.\S+")


def remover_dados_pessoais(texto: str) -> str:
    texto = _EMAIL.sub("[email removido]", texto or "")
    texto = _TELEFONE.sub("[telefone removido]", texto)
    texto = _URL.sub("[link removido]", texto)
    return texto


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c)).lower()


def chave_duplicata(titulo: str, empresa: str) -> tuple[str, str]:
    """RF05 — par (título, empresa) normalizado: sem acento, sem códigos de
    requisição como "[1310]" ou "- 117063", sem pontuação."""
    t = _sem_acento(titulo)
    t = re.sub(r"\[[^\]]*\]", " ", t)
    t = re.sub(r"[-–]\s*\d{4,}\s*$", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    e = re.sub(r"[^a-z0-9 ]+", " ", _sem_acento(empresa)).split()
    return t, (e[0] if e else "")


# --------------------------------------------------------------------------
# Perfis de vaga (RF31) — regras transparentes por título, com desempate
# pela categoria de habilidade dominante
# --------------------------------------------------------------------------
_REGRAS_PERFIL = [
    ("dados_ia", r"cientista|ciencia de dados|analista de dados|engenheiro de dados|engenharia de dados|\bbi\b|"
                 r"analytics|inteligencia artificial|\bia\b|machine learning|estatistic|inteligencia de mercado|"
                 r"inteligencia logistica"),
    ("industria", r"automac|eletronic|embarcad|firmware|industrial|\bclp\b|\bplc\b|\bmes\b|montagem de servidores|"
                  r"impressao 3d|\bcnc\b"),
    ("desenvolvimento", r"desenvolv|program|software|\bsw\b|full.?stack|front|back.?end|mobile|android|\bios\b|\bweb\b|"
                        r"java|python|\.net|node|tech lead|engenharia de software|\bqa\b|teste|testador|\bux\b|\bui\b"),
    ("infraestrutura", r"suporte|\bredes?\b|infraestrutura|telecom|fibra|help ?desk|service ?desk|tecnico de campo|"
                       r"campo em ti|\bn[123]\b|nivel|data center|seguranca da informacao|cloud|devops|almoxarife \(ti\)"),
    ("corporativo", r"\berp\b|\bsap\b|totvs|protheus|governanca|gerente|gestao de projetos|pmo|project manager|"
                    r"negocios|especialista de ti"),
]
_PERFIL_POR_CATEGORIA = {
    "LINGUAGENS": "desenvolvimento", "WEB_MOBILE": "desenvolvimento", "ENG_SOFTWARE": "desenvolvimento",
    "DADOS": "dados_ia", "IA": "dados_ia", "INFRA": "infraestrutura", "INDUSTRIA": "industria",
    "FUNDAMENTOS": "desenvolvimento", "PROFISSIONAL": "corporativo",
}


# Funções que não são de tecnologia mesmo quando a descrição cita termos técnicos
# (ex.: vendedor de produtos de informática). Regra explícita e auditável.
_FUNCAO_NAO_TECNICA = re.compile(
    r"\b(vendedor|vendedora|vendador|vendas|venda|sales|comercial|promotor|representante|"
    r"executivo de (vendas|contas|negocios)|assessor pedagogico|assessor de desenvolvimento|"
    r"recursos humanos|desenvolvimento humano|treinamento e desenvolvimento|t&d|recrutador|"
    r"imobiliari[oa]|cooperativismo|embalagens|operador de maquina|op de maquina)\b"
)


def funcao_nao_tecnica(titulo: str) -> bool:
    return bool(_FUNCAO_NAO_TECNICA.search(_sem_acento(titulo)))


# Título que identifica função de TI: permite aceitar vagas de descrição curta
# com uma única habilidade técnica reconhecida (ex.: "Técnico de Telecomunicações").
_TITULO_TI = re.compile(
    r"desenvolv|program|software|\bsw\b|sistemas?\b|\bti\b|t\.i|tecnologia|dados|suporte|\bredes?\b|"
    r"infraestrutura|telecom|fibra|servidor|teste|\bqa\b|automac|embarcad|eletronic|cloud|devops|seguranca da informacao"
)


def titulo_de_ti(titulo: str) -> bool:
    return bool(_TITULO_TI.search(_sem_acento(titulo)))


ORDEM_PERFIS = ("desenvolvimento", "dados_ia", "infraestrutura", "industria", "corporativo")  # mesma ordem de graph.hetero.PERFIS


def atribuir_perfil(titulo: str, habilidades: set[str], ont: Ontologia) -> str:
    t = _sem_acento(titulo)
    for perfil, padrao in _REGRAS_PERFIL:
        if re.search(padrao, t):
            return perfil
    cats = Counter(_PERFIL_POR_CATEGORIA[ont.habilidades[s].categoria] for s in sorted(habilidades))
    if not cats:
        return ORDEM_PERFIS[0]
    # empate decidido pela ordem fixa dos perfis, e não pela ordem de um conjunto (que muda a cada execução)
    return max(cats, key=lambda p: (cats[p], -ORDEM_PERFIS.index(p)))


# --------------------------------------------------------------------------
def executar() -> dict:
    cfg = carregar_config()
    ont = Ontologia(caminho("ontologia"))
    norm = Normalizador(ont, limiar=cfg["normalizacao"]["limiar_fuzzy"],
                        tamanho_minimo_fuzzy=cfg["normalizacao"]["tamanho_minimo_fuzzy"])
    out = processados()
    nao_tecnicas = set(cfg["filtro_vagas"]["categorias_nao_tecnicas"])

    # ---------------- disciplinas ----------------
    disciplinas = json.loads((out / "disciplinas.json").read_text(encoding="utf-8"))
    auditoria, todas_oc_disc = [], []
    disc_hab = {}
    for d in disciplinas:
        texto = f"{titulo_pt(d['nome'])}. {d['ementa']}"
        oc = norm.extrair(texto, doc_id=d["id"], modo="ementa")
        todas_oc_disc.extend(oc)
        resolvidas = [o for o in oc if o.skill_id]
        agreg = {}
        for o in resolvidas:
            a = agreg.setdefault(o.skill_id, {"skill": o.skill_id, "ocorrencias": 0, "camadas": set(), "escore_max": 0.0, "termos": set()})
            a["ocorrencias"] += 1
            a["camadas"].add(o.camada)
            a["escore_max"] = max(a["escore_max"], o.escore)
            a["termos"].add(o.termo_original.strip())
        disc_hab[d["id"]] = {
            "texto": texto,
            "fonte_ementa": d["fonte_ementa"],
            "habilidades": [
                {**v, "camadas": sorted(v["camadas"]), "termos": sorted(v["termos"])} for v in agreg.values()
            ],
            "evidencias": [
                {"skill": o.skill_id, "inicio": o.inicio, "fim": o.fim, "termo": o.termo_original} for o in resolvidas
            ],
        }
        auditoria.extend(ocorrencias_para_linhas(oc, "disciplina"))

    # ---------------- vagas ----------------
    bruto = json.loads(caminho("vagas_brutas").read_text(encoding="utf-8"))
    cidades = set(cfg["filtro_vagas"]["cidades_aceitas"])
    min_tec = cfg["filtro_vagas"]["min_habilidades_tecnicas"]
    aceitas, descartadas, todas_oc_vagas = [], [], []
    vistos_url, vistos_par = set(), {}
    for v in bruto["vagas"]:
        motivo = None
        if v["url"] in vistos_url:
            motivo = "duplicada (URL)"
        par = chave_duplicata(v["titulo"], v.get("empresa", ""))
        if motivo is None and par in vistos_par:
            motivo = f"duplicada (título, empresa) de {vistos_par[par]}"
        if motivo is None and _sem_acento(v.get("cidade", "")) not in cidades:
            motivo = "fora de Manaus (RN04)"
        descricao = remover_dados_pessoais(v.get("descricao", ""))
        texto = f"{v['titulo']}.\n{descricao}"
        empresa_tokens = re.split(r"[^\wÀ-ú]+", v.get("empresa", ""))
        oc = norm.extrair(texto, doc_id=v["id"], modo="vaga", excluir=[t for t in empresa_tokens if len(t) >= 3])
        hab = {o.skill_id for o in oc if o.skill_id}
        tec = {s for s in hab if ont.habilidades[s].categoria not in nao_tecnicas}
        if motivo is None and funcao_nao_tecnica(v["titulo"]):
            motivo = "não-TI: função não técnica pelo título"
        if motivo is None and len(tec) < min_tec and not (len(tec) >= 1 and titulo_de_ti(v["titulo"])):
            motivo = f"não-TI: {len(tec)} habilidade(s) técnica(s) < {min_tec} e título sem termo de TI"
        vistos_url.add(v["url"])
        if motivo is None:
            vistos_par[par] = v["id"]
        registro = {
            "id": v["id"], "url": v["url"], "titulo": v["titulo"], "empresa": v.get("empresa", ""),
            "cidade": v.get("cidade", ""), "data_publicacao": v.get("data_publicacao") or v.get("data_publicacao_relativa", ""),
            "data_coleta": v.get("data_coleta", ""),
        }
        if motivo:
            descartadas.append({**registro, "motivo": motivo, "habilidades_tecnicas": sorted(tec)})
            continue
        todas_oc_vagas.extend(oc)
        auditoria.extend(ocorrencias_para_linhas(oc, "vaga"))
        aceitas.append({
            **registro,
            "perfil": atribuir_perfil(v["titulo"], tec, ont),
            "habilidades": sorted(hab),
            "habilidades_tecnicas": sorted(tec),
            "texto": texto,
        })

    # ---------------- relatórios ----------------
    with open(out / "auditoria_normalizacao.csv", "w", newline="", encoding="utf-8") as f:
        campos = ["tipo_documento", "doc_id", "termo_original", "skill_id", "camada", "escore", "sinonimo", "inicio", "fim"]
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(auditoria)
    todas = todas_oc_disc + todas_oc_vagas
    quarentena = relatorio_nao_resolvidos(todas)
    with open(out / "nao_resolvidos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["termo", "frequencia"])
        w.writerows(quarentena)

    camadas = Counter(o.camada for o in todas)
    cob_vagas = cobertura(todas_oc_vagas, cfg["normalizacao"]["frequencia_minima_cobertura"])
    perfis = Counter(v["perfil"] for v in aceitas)
    resumo = {
        "limiar_fuzzy": norm.limiar,
        "habilidades_na_ontologia": len(ont.habilidades),
        "categorias": len(ont.categorias),
        "sinonimos": sum(len(h.aliases) + len(h.aliases_cs) for h in ont.habilidades.values()),
        "decisoes": dict(camadas),
        "vagas_brutas": len(bruto["vagas"]),
        "vagas_aceitas": len(aceitas),
        "vagas_descartadas": Counter(d["motivo"].split(":")[0].split(" de ")[0] for d in descartadas),
        "vagas_por_perfil": dict(perfis),
        "arestas_ensina": sum(len(v["habilidades"]) for v in disc_hab.values()),
        "arestas_exige": sum(len(v["habilidades"]) for v in aceitas),
        "habilidades_ensinadas": len({h["skill"] for v in disc_hab.values() for h in v["habilidades"]}),
        "habilidades_demandadas": len({s for v in aceitas for s in v["habilidades"]}),
        "cobertura_RNF18_vagas": cob_vagas,
        "quarentena_top20": quarentena[:20],
    }
    (out / "disciplinas_habilidades.json").write_text(json.dumps(disc_hab, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "vagas.json").write_text(json.dumps(aceitas, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "vagas_descartadas.json").write_text(json.dumps(descartadas, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "resumo_normalizacao.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    return resumo


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    r = executar()
    print(json.dumps({k: v for k, v in r.items() if k != "quarentena_top20"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
