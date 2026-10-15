"""Protocolo experimental (RF24, RF36–RF40).

Para cada semente: as arestas disciplina-ensina-skill são divididas em treino
(70%), validação (10%) e teste (20%) sem vazamento — o grafo usado no treino e
na inferência contém apenas as arestas de treino. Todos os modelos são
avaliados nas mesmas partições, em dois cenários:

* texto_completo — as ementas são usadas na íntegra, inclusive os trechos que
  originaram as arestas de teste. Mede a recuperação de vínculos explícitos.
* texto_mascarado — os trechos de ementa que evidenciam as arestas ocultas
  (validação e teste) são apagados antes de calcular qualquer atributo. Mede a
  inferência de vínculos latentes, que é o objetivo da predição de enlaces: o
  texto não "entrega" a resposta a nenhum modelo.

Métricas por consulta de habilidade (RF26): para cada habilidade com arestas
de teste, as disciplinas candidatas (excluídas as já ligadas a ela no treino e
na validação) são ordenadas pelo escore; calcula-se Precision@k e Recall@k
para k em {1, 3, 5, 10}, com desempate aleatório reprodutível, e a AUC ROC
global. Os resultados são agregados em média e desvio padrão entre sementes,
com teste de Wilcoxon pareado entre a GNN e as linhas de base.

Uso:  python -m edutrack.model.evaluate
"""
from __future__ import annotations

import csv
import json
import statistics
import time
from collections import defaultdict

import numpy as np

from edutrack.config import artefatos, carregar_config
from edutrack.graph.hetero import construir, carregar_dados
from edutrack.green.energy import RastreadorEnergia, registrar
from edutrack.model import baselines
from edutrack.model.sage import Hiper, auc, escores, treinar

MODELOS = ("GraphSAGE + texto (híbrido)", "GraphSAGE (GNN)", "GNN sem mensagens (L=0)", "TF-IDF (cosseno)",
           "Coocorrência (heurística)", "Popularidade")
PRINCIPAIS = ("GraphSAGE + texto (híbrido)", "GraphSAGE (GNN)")
CENARIOS = ("texto_completo", "texto_mascarado")


def dividir(arestas: np.ndarray, frac_val: float, frac_teste: float, semente: int):
    rng = np.random.default_rng(semente)
    perm = rng.permutation(len(arestas))
    n_te = max(1, int(round(frac_teste * len(arestas))))
    n_va = max(1, int(round(frac_val * len(arestas))))
    return arestas[perm[n_te + n_va:]], arestas[perm[n_te: n_te + n_va]], arestas[perm[:n_te]]


def textos_mascarados(dados: dict, ocultas: set[tuple[str, str]]) -> dict[str, str]:
    out = {}
    for did, info in dados["disc_hab"].items():
        chars = list(info["texto"])
        for ev in info["evidencias"]:
            if (did, ev["skill"]) in ocultas:
                for i in range(ev["inicio"], min(ev["fim"], len(chars))):
                    chars[i] = " "
        out[did] = "".join(chars)
    return out


def avaliar_ranking(S: np.ndarray, teste: np.ndarray, excluir: set, ks, semente: int) -> dict:
    rng = np.random.default_rng(semente)
    nd, ns = S.shape
    por_skill = defaultdict(set)
    for d, s in teste.tolist():
        por_skill[s].add(d)
    P = {k: [] for k in ks}
    R = {k: [] for k in ks}
    for s in sorted(por_skill):
        rel = por_skill[s]
        cand = np.array([d for d in range(nd) if (d, s) not in excluir])
        ordem = cand[np.lexsort((rng.random(len(cand)), -S[cand, s]))]
        for k in ks:
            hits = len(set(ordem[:k].tolist()) & rel)
            P[k].append(hits / k)
            R[k].append(hits / len(rel))
    conhecidos = excluir | set(map(tuple, teste.tolist()))
    neg = np.array([(d, s) for d in range(nd) for s in range(ns) if (d, s) not in conhecidos])
    return {
        **{f"P@{k}": float(np.mean(P[k])) for k in ks},
        **{f"R@{k}": float(np.mean(R[k])) for k in ks},
        "AUC": auc(S[teste[:, 0], teste[:, 1]], S[neg[:, 0], neg[:, 1]]),
        "consultas": len(por_skill),
    }


def executar() -> dict:
    cfg = carregar_config()
    hp_h = Hiper.de_config(cfg)                                            # modelo da aplicação (híbrido)
    hp = Hiper(**{**hp_h.__dict__, "decodificador_hibrido": False})        # GNN pura
    hp0 = Hiper(**{**hp.__dict__, "camadas": 0})                           # ablação sem mensagens
    ks = cfg["avaliacao"]["k"]
    sementes = cfg["avaliacao"]["sementes"]
    dados = carregar_dados()
    ont = dados["ont"]
    g0 = construir(dados, semente=42)
    di, si = g0.idx("disciplina"), g0.idx("skill")
    ids_d, ids_s = g0.nos["disciplina"]["ids"], g0.nos["skill"]["ids"]
    todas = np.array([(di[d], si[h["skill"]]) for d, v in dados["disc_hab"].items() for h in v["habilidades"]], dtype=int)
    textos_vaga = [v["texto"] for v in dados["vagas"]]

    por_semente = []
    tempos = defaultdict(list)
    epocas = []
    for semente in sementes:
        tr, va, te = dividir(todas, cfg["avaliacao"]["fracao_validacao"], cfg["avaliacao"]["fracao_teste"], semente)
        excluir = set(map(tuple, tr.tolist())) | set(map(tuple, va.tolist()))
        ocultas_ids = {(ids_d[d], ids_s[s]) for d, s in np.vstack([va, te]).tolist()}
        visiveis = [(ids_d[d], ids_s[s]) for d, s in tr.tolist()]
        reg = {"semente": semente, "treino": len(tr), "validacao": len(va), "teste": len(te), "resultados": {}}
        for cenario in CENARIOS:
            textos = textos_mascarados(dados, ocultas_ids) if cenario == "texto_mascarado" else None
            g = construir(dados, textos_disciplina=textos, arestas_ensina=visiveis, semente=semente)
            tdisc = [(textos or {}).get(d, dados["disc_hab"][d]["texto"]) for d in ids_d]
            S = {}
            t0 = time.perf_counter()
            S["TF-IDF (cosseno)"] = C = baselines.tfidf(tdisc, ont, textos_vaga)
            tempos["tfidf_total_s"].append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            rh = treinar(g, tr, va, hp_h, semente, C=C)
            tempos["treino_hibrido_s"].append(time.perf_counter() - t0)
            epocas.append(rh.melhor_epoca)
            t0 = time.perf_counter()
            S["GraphSAGE + texto (híbrido)"] = escores(rh.modelo, g, tr, C)
            tempos["inferencia_hibrido_s"].append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            r = treinar(g, tr, va, hp, semente)
            tempos["treino_gnn_s"].append(time.perf_counter() - t0)
            S["GraphSAGE (GNN)"] = escores(r.modelo, g, tr)
            r0 = treinar(g, tr, va, hp0, semente)
            S["GNN sem mensagens (L=0)"] = escores(r0.modelo, g, tr)
            S["Coocorrência (heurística)"] = baselines.coocorrencia(g, tr)
            S["Popularidade"] = baselines.popularidade(tr, len(ids_d), len(ids_s))
            reg["resultados"][cenario] = {m: avaliar_ranking(S[m], te, excluir, ks, semente) for m in MODELOS}
        por_semente.append(reg)

    # ---------------- agregação ----------------
    metricas = [f"P@{k}" for k in ks] + [f"R@{k}" for k in ks] + ["AUC"]
    agregado = {c: {m: {} for m in MODELOS} for c in CENARIOS}
    for c in CENARIOS:
        for m in MODELOS:
            for met in metricas:
                vals = [r["resultados"][c][m][met] for r in por_semente]
                agregado[c][m][met] = {"media": float(np.mean(vals)), "dp": float(np.std(vals, ddof=1))}
    testes = {}
    try:
        from scipy.stats import wilcoxon
        for c in CENARIOS:
            for principal in PRINCIPAIS:
                for base in MODELOS:
                    if base == principal or (principal == "GraphSAGE (GNN)" and base == "GraphSAGE + texto (híbrido)"):
                        continue
                    for met in ("P@1", "R@5", "AUC"):
                        a = [r["resultados"][c][principal][met] for r in por_semente]
                        b = [r["resultados"][c][base][met] for r in por_semente]
                        dif = np.array(a) - np.array(b)
                        p = float(wilcoxon(a, b).pvalue) if np.any(dif != 0) else 1.0
                        testes[f"{c} | {principal} vs {base} | {met}"] = {"diferenca_media": float(dif.mean()), "p_valor": p}
    except Exception as exc:  # pragma: no cover
        testes["erro"] = str(exc)

    resultado = {
        "protocolo": {
            "arestas_ensina": int(len(todas)), "particao": "70/10/20 (treino/validação/teste)",
            "sementes": sementes, "k": ks, "cenarios": list(CENARIOS), "modelos": list(MODELOS),
            "hiperparametros_gnn": hp.__dict__, "hiperparametros_hibrido": hp_h.__dict__,
        },
        "agregado": agregado,
        "testes_wilcoxon": testes,
        "tempos": {k: {"media": float(np.mean(v)), "dp": float(np.std(v, ddof=1)), "n": len(v)} for k, v in tempos.items()},
        "melhor_epoca_mediana": int(statistics.median(epocas)),
        "por_semente": por_semente,
    }
    return resultado


def salvar(resultado: dict) -> None:
    pasta = artefatos() / "metrics"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "avaliacao.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    ks = resultado["protocolo"]["k"]
    with open(pasta / "tabela_comparativa.csv", "w", newline="", encoding="utf-8") as f:  # RF39
        w = csv.writer(f)
        cab = ["cenario", "modelo"] + [f"P@{k}" for k in ks] + [f"R@{k}" for k in ks] + ["AUC"]
        w.writerow(cab)
        for c, por_modelo in resultado["agregado"].items():
            for m, mets in por_modelo.items():
                w.writerow([c, m] + [f"{mets[x]['media']:.3f} ± {mets[x]['dp']:.3f}" for x in cab[2:]])


def main() -> None:
    with RastreadorEnergia("avaliacao_experimental") as r:
        resultado = executar()
    resultado["energia"] = r.medicao.__dict__
    salvar(resultado)
    registrar([r.medicao], "energia_avaliacao.json")
    for c, por_modelo in resultado["agregado"].items():
        print(f"\n== {c}")
        for m, mets in por_modelo.items():
            print(f"  {m:28} " + "  ".join(f"{k}={v['media']:.3f}±{v['dp']:.3f}" for k, v in mets.items()))
    print("\nWilcoxon:", json.dumps(resultado["testes_wilcoxon"], ensure_ascii=False, indent=1))
    print("tempos:", resultado["tempos"], "| época mediana:", resultado["melhor_epoca_mediana"])
    print("energia:", r.medicao)


if __name__ == "__main__":
    main()
