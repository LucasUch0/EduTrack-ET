"""Executa o pipeline completo a partir dos dados brutos versionados (RNF26).

    python scripts/run_pipeline.py            # PPC -> normalização -> avaliação -> grafo e modelo final
    python scripts/run_pipeline.py --rapido   # pula a avaliação de 20 sementes (usa a existente)
    python scripts/run_pipeline.py --forcar   # refaz todas as etapas, ignorando o cache

Cache em disco (RNF07): cada etapa guarda em artifacts/cache/etapas.json a impressão
digital (SHA-256) das suas entradas — arquivos de dados, config.yaml e o código da
própria etapa. Se nada mudou e as saídas existem, a etapa é reaproveitada.

A coleta de vagas não é refeita aqui (ver edutrack/collect/scrape_talent.py).
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from edutrack.config import artefatos, caminho, processados  # noqa: E402
from edutrack.green.energy import RastreadorEnergia, registrar  # noqa: E402
from edutrack.model import evaluate, train_final  # noqa: E402
from edutrack.normalize import pipeline  # noqa: E402
from edutrack.parse import parse_ppc  # noqa: E402

CACHE = artefatos() / "cache" / "etapas.json"


def _codigo(*pastas: str) -> list[Path]:
    return sorted(p for d in pastas for p in (RAIZ / "edutrack" / d).glob("*.py")) + [RAIZ / "edutrack" / "config.py"]


def etapas() -> list[dict]:
    """Entradas e saídas de cada etapa, na ordem de execução."""
    proc, art = processados(), artefatos()
    cfg = RAIZ / "config.yaml"
    return [
        {"nome": "extracao_ppc", "entradas": [cfg, caminho("ppc_pdf"), caminho("grade"), caminho("ementas_referencia")]
         + _codigo("parse", "core"), "saidas": [proc / "disciplinas.json", proc / "cobertura_ppc.json"]},
        {"nome": "normalizacao", "entradas": [cfg, caminho("ontologia"), caminho("vagas_brutas"), proc / "disciplinas.json"]
         + _codigo("normalize", "core"),
         "saidas": [proc / f for f in ("disciplinas_habilidades.json", "vagas.json", "resumo_normalizacao.json",
                                       "auditoria_normalizacao.csv", "nao_resolvidos.csv")]},
        {"nome": "avaliacao", "entradas": [cfg, caminho("prerequisitos"), caminho("ontologia"), proc / "disciplinas.json",
                                           proc / "disciplinas_habilidades.json", proc / "vagas.json"]
         + _codigo("model", "graph", "core"),
         "saidas": [art / "metrics" / "avaliacao.json", art / "metrics" / "tabela_comparativa.csv"]},
        {"nome": "modelo_final", "entradas": [cfg, caminho("prerequisitos"), caminho("ontologia"), proc / "disciplinas.json",
                                              proc / "disciplinas_habilidades.json", proc / "vagas.json",
                                              art / "metrics" / "avaliacao.json"] + _codigo("model", "graph", "core"),
         "saidas": [art / "graph" / "grafo.npz", art / "model" / "afinidade_gnn.npy", art / "model" / "afinidade_tfidf.npy",
                    art / "model" / "hiperparametros.json"]},
    ]


def impressao(arquivos: list[Path]) -> str:
    h = hashlib.sha256()
    for p in arquivos:
        h.update(str(p.relative_to(RAIZ)).encode())
        h.update(p.read_bytes() if p.exists() else b"<ausente>")
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true", help="não refaz a avaliação experimental")
    ap.add_argument("--forcar", action="store_true", help="ignora o cache e refaz todas as etapas")
    a = ap.parse_args()
    t0 = time.perf_counter()
    cache = {} if a.forcar or not CACHE.exists() else json.loads(CACHE.read_text(encoding="utf-8"))
    medicoes = []

    def rodar(etapa: dict, funcao) -> None:
        digital = impressao(etapa["entradas"])
        if cache.get(etapa["nome"]) == digital and all(p.exists() for p in etapa["saidas"]):
            print(f"[cache] {etapa['nome']}: entradas inalteradas, saídas reaproveitadas")
            return
        t = time.perf_counter()
        funcao()
        cache[etapa["nome"]] = impressao(etapa["entradas"])  # recalculada: a etapa pode ter gerado entradas da seguinte
        print(f"[feito] {etapa['nome']} em {time.perf_counter() - t:.1f} s")

    e = {x["nome"]: x for x in etapas()}

    def extrair():
        with RastreadorEnergia("extracao_ppc") as r:
            parse_ppc.main()
        medicoes.append(r.medicao)

    def normalizar():
        with RastreadorEnergia("normalizacao") as r:
            resumo = pipeline.executar()
        medicoes.append(r.medicao)
        print(f"normalização: {resumo['vagas_aceitas']} vagas, {resumo['arestas_ensina']} arestas ensina, "
              f"cobertura RNF18 {resumo['cobertura_RNF18_vagas']['cobertura']:.1%}")

    rodar(e["extracao_ppc"], extrair)
    rodar(e["normalizacao"], normalizar)
    if medicoes:
        registrar(medicoes, "energia_preparacao.json")
    if not a.rapido:
        rodar(e["avaliacao"], evaluate.main)
    rodar(etapas()[3], train_final.main)  # entradas reavaliadas depois da avaliação
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    print(f"pipeline concluído em {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
