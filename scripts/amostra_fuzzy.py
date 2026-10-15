"""Gera a amostra para validação manual da camada aproximada (RNF19).

Inclui todas as decisões aceitas pela camada aproximada e os "quase acertos":
termos candidatos não resolvidos cuja razão de caracteres pura com algum
sinônimo é >= 0,80 (os pares que um limiar só de caracteres poderia aceitar).
A coluna 'rotulo' fica para os autores preencherem (correto / incorreto).
Saída: docs/amostra_validacao_fuzzy.csv
"""
import csv
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from edutrack.config import caminho, carregar_config, processados  # noqa: E402
from edutrack.normalize.normalize_skills import Normalizador, Ontologia, norm_termo  # noqa: E402


def main():
    cfg = carregar_config()
    ont = Ontologia(caminho("ontologia"))
    n = Normalizador(ont, limiar=cfg["normalizacao"]["limiar_fuzzy"])
    linhas, vistos = [], set()
    with open(processados() / "auditoria_normalizacao.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            chave = norm_termo(r["termo_original"])
            if chave in vistos:
                continue
            if r["camada"] == "fuzzy":
                vistos.add(chave)
                linhas.append([r["termo_original"], r["sinonimo"], r["skill_id"], r["escore"], "aceito", ""])
            elif r["camada"] == "nao_resolvido" and len(chave) >= 5:
                top = n.similaridade_bruta(r["termo_original"], k=1)
                if top and top[0][1] >= 0.80:
                    vistos.add(chave)
                    s, razao = top[0]
                    linhas.append([r["termo_original"], s, n._mapa[s], f"{razao:.4f}", "rejeitado", ""])
    saida = RAIZ / "docs" / "amostra_validacao_fuzzy.csv"
    with open(saida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["termo", "sinonimo_mais_proximo", "habilidade", "razao_caracteres", "decisao_do_sistema", "rotulo"])
        w.writerows(linhas)
    print(f"{len(linhas)} pares em {saida} ({sum(1 for l in linhas if l[4] == 'aceito')} aceitos)")


if __name__ == "__main__":
    main()
