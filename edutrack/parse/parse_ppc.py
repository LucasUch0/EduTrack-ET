"""Extração curricular do PPC (RF07–RF10a, RNF20, RNF21).

O documento de entrada é o "Programa de Disciplina" emitido pelo portal da
FAMETRO: um PDF em que cada disciplina começa por uma linha
``DISCIPLINA: <nome> CÓDIGO: <n> Nº CRÉDITOS: <n> CARGA HORÁRIA: <n>``.
O texto é segmentado ancorando nesse marcador em modo multilinha (RF07), e de
cada bloco saem nome, código, créditos, carga horária, período, ementa e
bibliografia (RF08). Blocos sem cabeçalho completo são descartados como
espúrios (RF09). Ao final, as disciplinas extraídas são cruzadas com a grade
declarada para verificar a contagem esperada (RF10) e sinalizar o que faltou
(RF10a / RNF21).

Uso:  python -m edutrack.parse.parse_ppc
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

from edutrack.config import caminho, carregar_config, processados

log = logging.getLogger("edutrack.ppc")

MARCADOR = re.compile(r"(?m)^\s*DISCIPLINA:")
CABECALHO = re.compile(
    r"DISCIPLINA:\s*(?P<nome>.+?)\s+C[ÓO]DIGO:\s*(?P<codigo>\d+)\s+N[º°o]\s*CR[ÉE]DITOS:\s*(?P<creditos>\d+)"
    r"\s+CARGA\s+HOR[ÁA]RIA:\s*(?P<ch>\d+)"
)
PERIODO = re.compile(r"PER[ÍI]ODO:\s*(\d+)")
CURRICULO = re.compile(r"CURR[ÍI]CULO:\s*(\S+)")
RODAPE = re.compile(r"(?s)Como validar o Programa de Disciplina:.*?(DATA DA EMISS[ÃA]O:[^\n]*\n?)")


def chave_nome(nome: str) -> str:
    s = unicodedata.normalize("NFD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()


def extrair_texto_pdf(pdf: Path) -> str:
    """Texto do PDF, página a página. Falhas de leitura não interrompem o
    pipeline (RNF20): a página problemática é registrada e ignorada."""
    import pdfplumber  # dependência só desta etapa

    partes = []
    try:
        doc = pdfplumber.open(str(pdf))
    except Exception as exc:  # PDF corrompido ou que não é PDF: registra e segue com a grade declarada
        log.warning("Não foi possível abrir %s como PDF (%s); seguindo sem o programa oficial.", pdf.name, exc)
        return ""
    with doc:
        for i, pag in enumerate(doc.pages):
            try:
                partes.append(pag.extract_text() or "")
            except Exception as exc:  # pragma: no cover - página malformada
                log.warning("Falha ao ler a página %s de %s: %s", i + 1, pdf.name, exc)
    return "\n".join(partes)


_INICIO_REFERENCIA = re.compile(
    r"^\s*(?:\d+\.\s*)+"                                   # itens numerados "1. "
    r"|^(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ' -]{1,40},\s)",  # ou linha iniciada por SOBRENOME,
    re.M,
)


def _itens_bibliografia(trecho: str) -> list[str]:
    trecho = re.sub(r"https?://\S+", "", trecho)
    trecho = re.sub(r"(?m)^\s*PROGRAMA DE DISCIPLINA\s*$", "", trecho)
    itens = _INICIO_REFERENCIA.split(trecho)
    out = []
    for it in itens:
        it = re.sub(r"\s+", " ", it).strip()
        if len(it) > 10:
            out.append(it)
    return out


def segmentar(texto: str) -> list[str]:
    """Divide o texto em blocos que começam no marcador ^DISCIPLINA: (RF07)."""
    texto = RODAPE.sub("\n", texto)
    pos = [m.start() for m in MARCADOR.finditer(texto)]
    return [texto[a:b] for a, b in zip(pos, pos[1:] + [len(texto)])]


def corrigir_espacamento(texto: str) -> str:
    """O PDF emitido pelo portal perde espaços em alguns trechos
    ("Pesquisa deMercado.Técnicas", "dePreços"). Reinsere o espaço entre
    minúscula e maiúscula seguida de minúscula e depois de ponto final colado
    a uma maiúscula."""
    texto = re.sub(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Ý][a-zà-ÿ])", " ", texto)
    texto = re.sub(r"(?<=[a-zà-ÿ])\.(?=[A-ZÀ-Ý])", ". ", texto)
    return texto


def parse_bloco(bloco: str) -> dict | None:
    m = CABECALHO.search(bloco)
    if not m:
        return None
    nome = re.sub(r"\s+", " ", m.group("nome")).strip()
    if len(nome) <= 1:  # RF09: token de caractere único
        return None
    per = PERIODO.search(bloco)
    cur = CURRICULO.search(bloco)
    em = re.search(r"\bEMENTA\b\s*(.*?)\s*BIBLIOGRAFIA\s+B[ÁA]SICA", bloco, re.S)
    bb = re.search(r"BIBLIOGRAFIA\s+B[ÁA]SICA\s*(.*?)\s*BIBLIOGRAFIA\s+COMPLEMENTAR", bloco, re.S)
    bc = re.search(r"BIBLIOGRAFIA\s+COMPLEMENTAR\s*(.*)$", bloco, re.S)
    ementa = corrigir_espacamento(re.sub(r"\s+", " ", em.group(1)).strip()) if em else ""
    return {
        "nome": nome,
        "codigo": m.group("codigo"),
        "creditos": int(m.group("creditos")),
        "carga_horaria": int(m.group("ch")),
        "periodo": int(per.group(1)) if per else None,
        "curriculo": cur.group(1) if cur else None,
        "ementa": ementa,
        "bibliografia_basica": _itens_bibliografia(bb.group(1)) if bb else [],
        "bibliografia_complementar": _itens_bibliografia(bc.group(1)) if bc else [],
    }


def extrair_ppc(pdf: Path) -> tuple[list[dict], list[str]]:
    texto = extrair_texto_pdf(pdf)
    validas, espurias = [], []
    for bloco in segmentar(texto):
        d = parse_bloco(bloco)
        if d is None or not d["ementa"]:
            espurias.append(bloco[:120])
            continue
        validas.append(d)
    return validas, espurias


def montar_base_curricular(pdf: Path | None = None) -> dict:
    """Une programa oficial + grade declarada + ementas de referência."""
    cfg = carregar_config()
    grade = json.loads(caminho("grade").read_text(encoding="utf-8"))
    refs = json.loads(caminho("ementas_referencia").read_text(encoding="utf-8"))["ementas"]
    pdf = pdf or caminho("ppc_pdf")

    extraidas, espurias = ([], [])
    if pdf and Path(pdf).exists():
        extraidas, espurias = extrair_ppc(Path(pdf))
    else:
        log.warning("PDF do PPC não encontrado em %s; usando apenas a grade declarada.", pdf)
    por_nome = {chave_nome(d["nome"]): d for d in extraidas}

    disciplinas, sem_programa, divergencias = [], [], []
    usados = set()
    for g in grade["disciplinas"]:
        k = chave_nome(g["nome"])
        oficial = por_nome.get(k)
        reg = {
            "id": g["id"],
            "nome": g["nome"],
            "periodo": g["periodo"],
            "codigo": None,
            "carga_horaria": None,
            "creditos": None,
            "ementa": "",
            "bibliografia": [],
            "fonte_ementa": None,
        }
        if oficial:
            usados.add(k)
            if oficial["periodo"] and oficial["periodo"] != g["periodo"]:
                divergencias.append({"disciplina": g["nome"], "periodo_grade": g["periodo"], "periodo_programa": oficial["periodo"]})
                reg["periodo"] = oficial["periodo"]  # documento oficial prevalece
            reg.update({
                "codigo": oficial["codigo"], "carga_horaria": oficial["carga_horaria"], "creditos": oficial["creditos"],
                "ementa": oficial["ementa"],
                "bibliografia": oficial["bibliografia_basica"] + oficial["bibliografia_complementar"],
                "fonte_ementa": "programa_oficial",
            })
        elif g["id"] in refs:
            reg.update({"ementa": refs[g["id"]], "fonte_ementa": "referencia"})
            sem_programa.append(g["nome"])
        else:
            reg["fonte_ementa"] = "ausente"
            sem_programa.append(g["nome"])
        if "periodo_historico" in g:
            reg["periodo_historico"] = g["periodo_historico"]
        disciplinas.append(reg)

    # disciplinas presentes no PDF mas ausentes da grade declarada: entram como stub identificável (RF10a)
    for k, d in por_nome.items():
        if k not in usados:
            slug = re.sub(r"[^a-z0-9]+", "_", chave_nome(d["nome"]).lower()).strip("_")
            disciplinas.append({
                "id": slug, "nome": d["nome"], "periodo": d["periodo"], "codigo": d["codigo"],
                "carga_horaria": d["carga_horaria"], "creditos": d["creditos"], "ementa": d["ementa"],
                "bibliografia": d["bibliografia_basica"] + d["bibliografia_complementar"],
                "fonte_ementa": "programa_oficial", "fora_da_grade_declarada": True,
            })

    esperadas = cfg["ppc"]["disciplinas_esperadas"]
    periodos = sorted({d["periodo"] for d in disciplinas if d["periodo"]})
    por_periodo = {p: sum(1 for d in disciplinas if d["periodo"] == p) for p in range(1, cfg["ppc"]["periodos_esperados"] + 1)}
    cobertura = {
        "curriculo": cfg["ppc"]["curriculo"],
        "disciplinas_identificadas": len(disciplinas),
        "disciplinas_esperadas": esperadas,
        "divergencia_contagem": len(disciplinas) != esperadas,  # RF10
        "faltantes": max(esperadas - len(disciplinas), 0),
        "periodos_presentes": len(periodos),
        "periodos_esperados": cfg["ppc"]["periodos_esperados"],
        "disciplinas_por_periodo": por_periodo,
        "com_programa_oficial": sum(1 for d in disciplinas if d["fonte_ementa"] == "programa_oficial"),
        "com_ementa_referencia": sum(1 for d in disciplinas if d["fonte_ementa"] == "referencia"),
        "sem_ementa": sum(1 for d in disciplinas if d["fonte_ementa"] == "ausente"),
        "extraidas_do_pdf": len(extraidas),
        "blocos_espurios_descartados": len(espurias),
        "divergencias_de_periodo": divergencias,
        "sem_programa_oficial": sem_programa,
        "declaracao_RNF21": f"{len(periodos)} de {cfg['ppc']['periodos_esperados']} períodos e "
                            f"{len(disciplinas)} de {esperadas} disciplinas",
    }
    if cobertura["divergencia_contagem"]:
        log.warning("Contagem de disciplinas divergente: %s identificadas, %s esperadas.", len(disciplinas), esperadas)
    return {"disciplinas": disciplinas, "cobertura": cobertura}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    base = montar_base_curricular()
    out = processados()
    (out / "disciplinas.json").write_text(json.dumps(base["disciplinas"], ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "cobertura_ppc.json").write_text(json.dumps(base["cobertura"], ensure_ascii=False, indent=1), encoding="utf-8")
    c = base["cobertura"]
    print(f"Disciplinas: {c['declaracao_RNF21']} | oficiais={c['com_programa_oficial']} "
          f"referência={c['com_ementa_referencia']} | espúrios descartados={c['blocos_espurios_descartados']}")


if __name__ == "__main__":
    main()
