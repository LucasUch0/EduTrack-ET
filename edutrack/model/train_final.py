"""Treina o modelo final usado pela aplicação e exporta os artefatos (RF21, RF25).

O modelo final usa todas as arestas disciplina-ensina-skill, com o número de
épocas igual à mediana das melhores épocas da avaliação (não há validação a
consultar). Também exporta a matriz TF-IDF, que a aplicação oferece como
modelo alternativo de afinidade, e escolhe o modelo padrão pelo desempenho no
cenário de vínculos latentes (texto mascarado) da avaliação.

Uso:  python -m edutrack.model.train_final
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from edutrack.config import artefatos, carregar_config
from edutrack.graph.hetero import construir, carregar_dados
from edutrack.green.energy import RastreadorEnergia, registrar
from edutrack.model import baselines
from edutrack.model.sage import Hiper, escores, sigmoid, treinar


def modelo_padrao(avaliacao: dict | None) -> tuple[str, str]:
    """'gnn' ou 'tfidf': o de maior Recall@5 médio no cenário mascarado."""
    if not avaliacao:
        return "gnn", "sem avaliação disponível"
    ag = avaliacao["agregado"]["texto_mascarado"]
    g = ag["GraphSAGE + texto (híbrido)"]["R@5"]["media"]
    t = ag["TF-IDF (cosseno)"]["R@5"]["media"]
    escolha = "gnn" if g >= t else "tfidf"
    return escolha, f"R@5 no cenário de vínculos latentes: GNN híbrida {g:.3f} x TF-IDF {t:.3f}"


def main() -> None:
    cfg = carregar_config()
    semente = cfg["semente_global"]
    pasta_m = artefatos() / "model"
    pasta_m.mkdir(parents=True, exist_ok=True)
    arq_aval = artefatos() / "metrics" / "avaliacao.json"
    avaliacao = json.loads(arq_aval.read_text(encoding="utf-8")) if arq_aval.exists() else None
    epocas = avaliacao["melhor_epoca_mediana"] if avaliacao else cfg["modelo"]["epocas"]

    medicoes = []
    with RastreadorEnergia("construcao_do_grafo") as r1:
        dados = carregar_dados()
        g = construir(dados, semente=semente)
        validacao = g.validar()
        g.salvar(artefatos() / "graph")
    medicoes.append(r1.medicao)
    (artefatos() / "graph" / "validacao.json").write_text(json.dumps(validacao, ensure_ascii=False, indent=1), encoding="utf-8")

    di, si = g.idx("disciplina"), g.idx("skill")
    todas = np.array([(di[d], si[h["skill"]]) for d, v in dados["disc_hab"].items() for h in v["habilidades"]], dtype=int)
    ids_d = g.nos["disciplina"]["ids"]
    tdisc = [dados["disc_hab"][d]["texto"] for d in ids_d]
    C = baselines.tfidf(tdisc, dados["ont"], [v["texto"] for v in dados["vagas"]])

    hp = Hiper.de_config(cfg)
    with RastreadorEnergia("treino_modelo_final") as r2:
        res = treinar(g, todas, None, hp, semente, epocas_fixas=epocas, C=C)
    medicoes.append(r2.medicao)
    with RastreadorEnergia("inferencia_modelo_final") as r3:
        S = escores(res.modelo, g, todas, C)
    medicoes.append(r3.medicao)

    np.savez_compressed(pasta_m / "modelo_gnn.npz", **res.modelo.p)
    np.save(pasta_m / "afinidade_gnn.npy", sigmoid(S))
    np.save(pasta_m / "afinidade_tfidf.npy", C)
    escolha, motivo = modelo_padrao(avaliacao)
    meta = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "semente": semente,
        "epocas": epocas,
        "hiperparametros": hp.__dict__,
        "beta_aprendido": float(res.modelo.p["dec.beta"][0]) if hp.decodificador_hibrido else None,
        "arestas_ensina_usadas": int(len(todas)),
        "ids_disciplina": ids_d,
        "ids_skill": g.nos["skill"]["ids"],
        "modelo_padrao": escolha,
        "motivo_modelo_padrao": motivo,
        "perda_final": res.historico[-1]["perda"] if res.historico else None,
        "segundos_treino": res.segundos,
    }
    (pasta_m / "hiperparametros.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    energia = registrar(medicoes, "energia_pipeline.json")
    print(f"modelo final: {epocas} épocas, {res.segundos:.2f}s | padrão={escolha} ({motivo})")
    print(f"energia: {energia['total_energia_wh']:.4f} Wh, {energia['total_co2_g']:.4f} gCO2")


if __name__ == "__main__":
    main()
