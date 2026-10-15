"""Mede o tempo de resposta da recomendação pela API em execução (RNF02: p95 <= 3 s em 30 execuções).

Uso (com a aplicação rodando em outro terminal):
    python scripts/medir_latencia.py                       # http://127.0.0.1:8000, 30 requisições
    python scripts/medir_latencia.py --url http://host:porta --n 30

Cada requisição usa uma seleção diferente de disciplinas (do 1º ao n-ésimo período, com perfis e
tamanhos de trilha alternados), para não medir só a mesma resposta. O resultado vai para
artifacts/metrics/latencia_api.json.
"""
import argparse
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
PERFIS = [None, "desenvolvimento", "dados_ia", "infraestrutura", "industria", "corporativo"]


def percentil(valores, p):
    v = sorted(valores)
    pos = (len(v) - 1) * p / 100
    i = int(pos)
    return v[i] if i + 1 >= len(v) else v[i] + (v[i + 1] - v[i]) * (pos - i)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    s = requests.Session()
    disciplinas = s.get(f"{a.url}/api/disciplinas", timeout=10).json()
    disciplinas = disciplinas.get("disciplinas", disciplinas) if isinstance(disciplinas, dict) else disciplinas
    s.post(f"{a.url}/api/trilha", json={"cursadas": []}, timeout=30)  # aquecimento (carga dos artefatos)
    tempos_ms, servidor_ms = [], []
    for i in range(a.n):
        ate = 1 + i % 8
        corpo = {"cursadas": [d["id"] for d in disciplinas if d["periodo"] <= ate],
                 "perfil": PERFIS[i % len(PERFIS)], "k": 3 + i % 8, "modelo": ("auto", "gnn", "tfidf")[i % 3]}
        t0 = time.perf_counter()
        r = s.post(f"{a.url}/api/trilha", json=corpo, timeout=30)
        tempos_ms.append((time.perf_counter() - t0) * 1000)
        r.raise_for_status()
        servidor_ms.append(float(r.headers.get("X-Tempo-Resposta-ms", "nan")))
    res = {
        "medido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": a.url, "requisicoes": a.n, "rota": "POST /api/trilha",
        "ponta_a_ponta_ms": {"p50": percentil(tempos_ms, 50), "p95": percentil(tempos_ms, 95),
                             "max": max(tempos_ms), "media": statistics.mean(tempos_ms)},
        "no_servidor_ms": {"p50": percentil(servidor_ms, 50), "p95": percentil(servidor_ms, 95), "max": max(servidor_ms)},
        "limite_RNF02_ms": 3000, "atende_RNF02": percentil(tempos_ms, 95) <= 3000,
        "plataforma": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
    }
    saida = RAIZ / "artifacts" / "metrics" / "latencia_api.json"
    saida.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    p = res["ponta_a_ponta_ms"]
    print(f"{a.n} requisições: p50 {p['p50']:.1f} ms, p95 {p['p95']:.1f} ms, máx {p['max']:.1f} ms "
          f"-> RNF02 {'atendido' if res['atende_RNF02'] else 'NÃO atendido'} ({saida.relative_to(RAIZ)})")
    sys.exit(0 if res["atende_RNF02"] else 1)


if __name__ == "__main__":
    main()
