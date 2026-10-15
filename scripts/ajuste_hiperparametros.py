"""Seleção de hiperparâmetros da GNN usando SOMENTE a AUC de validação.

Etapa 1: grade sobre camadas, dropout, taxa de aprendizado, projeção textual
compartilhada e peso da tarefa auxiliar (GNN pura). Etapa 2: com a melhor
configuração da etapa 1, grade sobre o peso inicial da similaridade textual
no decodificador híbrido. As sementes de ajuste (11 a 66) são distintas das
sementes de avaliação e o conjunto de teste nunca é consultado.

Resultado em artifacts/metrics/ajuste_hiperparametros.json.
Uso:  python scripts/ajuste_hiperparametros.py
"""
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from edutrack.graph.hetero import carregar_dados, construir  # noqa: E402
from edutrack.model import baselines  # noqa: E402
from edutrack.model.evaluate import dividir, textos_mascarados  # noqa: E402
from edutrack.model.sage import Hiper, auc, treinar  # noqa: E402

SEMENTES = [11, 22, 33, 44, 55, 66]


def preparar():
    dados = carregar_dados()
    g0 = construir(dados)
    di, si = g0.idx("disciplina"), g0.idx("skill")
    ids_d, ids_s = g0.nos["disciplina"]["ids"], g0.nos["skill"]["ids"]
    todas = np.array([(di[d], si[h["skill"]]) for d, v in dados["disc_hab"].items() for h in v["habilidades"]])
    tv = [v["texto"] for v in dados["vagas"]]
    casos = []
    for s in SEMENTES:
        tr, va, _ = dividir(todas, 0.1, 0.2, s)
        ocultas = {(ids_d[d], ids_s[k]) for d, k in np.vstack([va, dividir(todas, 0.1, 0.2, s)[2]]).tolist()}
        for cen in ("texto_completo", "texto_mascarado"):
            textos = textos_mascarados(dados, ocultas) if cen == "texto_mascarado" else None
            g = construir(dados, textos_disciplina=textos, arestas_ensina=[(ids_d[d], ids_s[k]) for d, k in tr.tolist()], semente=s)
            tdisc = [(textos or {}).get(d, dados["disc_hab"][d]["texto"]) for d in ids_d]
            C = baselines.tfidf(tdisc, dados["ont"], tv)
            conhecidos = set(map(tuple, tr.tolist())) | set(map(tuple, va.tolist()))
            neg = np.array([(d, k) for d in range(len(ids_d)) for k in range(len(ids_s)) if (d, k) not in conhecidos])
            casos.append({"semente": s, "cenario": cen, "g": g, "tr": tr, "va": va, "C": C,
                          "auc_tfidf": auc(C[va[:, 0], va[:, 1]], C[neg[:, 0], neg[:, 1]])})
    return casos


def avaliar(casos, hp):
    r = {"texto_completo": [], "texto_mascarado": []}
    for c in casos:
        res = treinar(c["g"], c["tr"], c["va"], hp, c["semente"], C=c["C"] if hp.decodificador_hibrido else None)
        r[c["cenario"]].append(max(h.get("auc_val", 0) for h in res.historico))
    return {k: float(np.mean(v)) for k, v in r.items()}


def main():
    casos = preparar()
    ref = {cen: float(np.mean([c["auc_tfidf"] for c in casos if c["cenario"] == cen])) for cen in ("texto_completo", "texto_mascarado")}
    print("TF-IDF (referência, sem ajuste):", ref)
    grade = {"camadas": [1, 2], "dropout": [0.0, 0.2], "taxa_aprendizado": [0.005, 0.01],
             "texto_compartilhado": [True, False], "peso_auxiliar_exige": [0.0, 0.5]}
    etapa1 = []
    for vals in itertools.product(*grade.values()):
        kw = dict(zip(grade.keys(), vals))
        t0 = time.perf_counter()
        a = avaliar(casos, Hiper(dim_oculta=32, dim_saida=32, epocas=300, paciencia=60, residual=True, **kw))
        etapa1.append({"hiperparametros": kw, "auc_val": a, "segundos": round(time.perf_counter() - t0, 1)})
        print(f"{a['texto_mascarado']:.3f} {a['texto_completo']:.3f} {kw}", flush=True)
    etapa1.sort(key=lambda r: -(r["auc_val"]["texto_mascarado"] + r["auc_val"]["texto_completo"]))
    melhor = etapa1[0]["hiperparametros"]
    etapa2 = []
    for beta in (1.0, 4.0, 8.0, 16.0):
        a = avaliar(casos, Hiper(dim_oculta=32, dim_saida=32, epocas=300, paciencia=60, residual=True,
                                 decodificador_hibrido=True, beta_inicial=beta, **{**melhor, "peso_auxiliar_exige": 0.5}))
        etapa2.append({"beta_inicial": beta, "auc_val": a})
        print(f"beta={beta}: {a}", flush=True)
    saida = RAIZ / "artifacts" / "metrics" / "ajuste_hiperparametros.json"
    saida.write_text(json.dumps({"sementes_de_ajuste": SEMENTES, "referencia_tfidf_auc_val": ref,
                                 "etapa1_gnn": etapa1, "etapa2_beta_hibrido": etapa2,
                                 "observacao": "AUC de validação na melhor época (otimista para os modelos treinados); "
                                               "o TF-IDF não tem ajuste. A comparação final é feita no teste."},
                                ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
