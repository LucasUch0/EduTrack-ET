"""Motor de recomendação de trilhas e diagnóstico curricular (RF26–RF35, RN03, RN05, RN07).

Tudo aqui é leitura de artefatos pré-processados: nada do que o estudante
informa é gravado (RF42, RN07). O perfil do estudante é só o conjunto de
disciplinas cursadas, usado como filtro em tempo de consulta.

Definições
----------
* Demanda de uma habilidade s no perfil de vagas P: w_s = |{vagas de P que exigem s}| / |P|.
* Aderência de um conjunto de habilidades H: soma(w_s, s em H) / soma(w_s, todas as s).
* Habilidades do estudante: as ligadas por aresta *ensina* explícita às disciplinas cursadas.
* Trilha (RF29): seleção gulosa de disciplinas ainda não cursadas que maximiza a
  demanda coberta por arestas explícitas — cobertura máxima ponderada, cujo
  algoritmo guloso tem garantia de aproximação (1 - 1/e) por ser submodular.
  Empates são desfeitos pela afinidade do modelo (GNN ou TF-IDF) com as
  lacunas ainda abertas. Uma disciplina só entra se seus pré-requisitos já
  foram cursados ou estão antes dela na trilha (RN03); se a melhor candidata
  estiver bloqueada, os pré-requisitos faltantes entram primeiro.
* Habilidades complementares: lacunas que nenhuma disciplina do PPC ensina;
  para cada uma, a GNN indica a disciplina de maior afinidade como apoio, desde
  que corroborada pelo mercado (a disciplina ensina uma habilidade que as vagas
  pedem junto com a lacuna) e acima do limiar configurado.

Complexidade da trilha: O(k * D * S) para k passos, D disciplinas e S habilidades.
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cached_property

import numpy as np

from edutrack.core.texto import titulo_pt
from edutrack.config import artefatos, caminho, carregar_config, processados
from edutrack.normalize.normalize_skills import Ontologia

NOMES_PERFIS = {
    "desenvolvimento": "Desenvolvimento de Software",
    "dados_ia": "Dados e Inteligência Artificial",
    "infraestrutura": "Infraestrutura, Redes e Suporte",
    "industria": "Automação Industrial e Embarcados",
    "corporativo": "Sistemas Corporativos e Gestão de TI",
}
NAO_RECOMENDAVEIS = {"estagio", "tcc", "optativa"}  # obrigatórias de fim de curso ou sem conteúdo fixo


class ErroEntrada(ValueError):
    pass


@dataclass
class Base:
    """Artefatos carregados uma única vez pela API."""

    disciplinas: list
    disc_hab: dict
    prereq: list
    vagas: list
    ont: Ontologia
    afinidade: dict  # modelo -> matriz D x S
    ids_d: list
    ids_s: list
    meta_modelo: dict

    @classmethod
    def carregar(cls) -> "Base":
        out = processados()
        meta = json.loads((artefatos() / "model" / "hiperparametros.json").read_text(encoding="utf-8"))
        return cls(
            disciplinas=json.loads((out / "disciplinas.json").read_text(encoding="utf-8")),
            disc_hab=json.loads((out / "disciplinas_habilidades.json").read_text(encoding="utf-8")),
            prereq=json.loads(caminho("prerequisitos").read_text(encoding="utf-8"))["arestas"],
            vagas=json.loads((out / "vagas.json").read_text(encoding="utf-8")),
            ont=Ontologia(caminho("ontologia")),
            afinidade={
                "gnn": np.load(artefatos() / "model" / "afinidade_gnn.npy"),
                "tfidf": np.load(artefatos() / "model" / "afinidade_tfidf.npy"),
            },
            ids_d=meta["ids_disciplina"],
            ids_s=meta["ids_skill"],
            meta_modelo=meta,
        )

    # ------------------------------------------------------------- índices
    @cached_property
    def idx_d(self) -> dict:
        return {k: i for i, k in enumerate(self.ids_d)}

    @cached_property
    def idx_s(self) -> dict:
        return {k: i for i, k in enumerate(self.ids_s)}

    @cached_property
    def disciplina(self) -> dict:
        return {d["id"]: d for d in self.disciplinas}

    @cached_property
    def ensina(self) -> dict[str, set]:
        return {d: {h["skill"] for h in v["habilidades"]} for d, v in self.disc_hab.items()}

    @cached_property
    def evidencias(self) -> dict[tuple, list]:
        return {(d, h["skill"]): h["termos"] for d, v in self.disc_hab.items() for h in v["habilidades"]}

    def ensina_tecnica(self, d: str) -> bool:
        """A disciplina ensina ao menos uma habilidade técnica (fora da categoria PROFISSIONAL)?"""
        nao_tec = set(carregar_config()["filtro_vagas"]["categorias_nao_tecnicas"])
        return any(self.ont.habilidades[s].categoria not in nao_tec for s in self.ensina.get(d, ()))

    @cached_property
    def requisitos(self) -> dict[str, set]:
        r = defaultdict(set)
        for p in self.prereq:
            r[p["disciplina"]].add(p["requer"])
        return r

    @cached_property
    def ensinadas(self) -> set:
        return set().union(*self.ensina.values()) if self.ensina else set()

    def modelo(self, nome: str | None) -> str:
        if nome in (None, "", "auto"):
            return self.meta_modelo.get("modelo_padrao", "tfidf")
        if nome not in self.afinidade:
            raise ErroEntrada(f"modelo desconhecido: {nome}")
        return nome

    def nome_skill(self, s: str) -> str:
        return self.ont.habilidades[s].nome

    # ------------------------------------------------------------- mercado
    def vagas_do_perfil(self, perfil: str | None) -> list:
        if perfil in (None, "", "todos"):
            return self.vagas
        if perfil not in NOMES_PERFIS:
            raise ErroEntrada(f"perfil desconhecido: {perfil}")
        return [v for v in self.vagas if v["perfil"] == perfil]

    def demanda(self, perfil: str | None = None) -> dict[str, float]:
        vs = self.vagas_do_perfil(perfil)
        if not vs:
            return {}
        c = Counter(s for v in vs for s in set(v["habilidades"]))
        return {s: n / len(vs) for s, n in c.items()}

    def aderencia(self, habilidades: set, w: dict) -> float:
        total = sum(w.values())
        return sum(w.get(s, 0.0) for s in habilidades) / total if total else 0.0

    # ------------------------------------------------------------- RF27
    def validar_cursadas(self, cursadas: list[str]) -> list[str]:
        desconhecidas = [c for c in cursadas if c not in self.disciplina]
        if desconhecidas:
            raise ErroEntrada(f"disciplinas desconhecidas: {', '.join(desconhecidas[:5])}")
        return list(dict.fromkeys(cursadas))

    def habilidades_de(self, disciplinas: list[str]) -> set:
        return set().union(*(self.ensina.get(d, set()) for d in disciplinas)) if disciplinas else set()

    # ------------------------------------------------------------- RF28–RF31
    def trilha(self, cursadas: list[str], perfil: str | None = None, k: int | None = None, modelo: str | None = None) -> dict:
        cfg = carregar_config()["recomendacao"]
        k = cfg["k_padrao"] if k is None else int(k)
        if not 1 <= k <= cfg["k_maximo"]:
            raise ErroEntrada(f"k deve estar entre 1 e {cfg['k_maximo']}")
        cursadas = self.validar_cursadas(cursadas)
        modelo = self.modelo(modelo)
        A = self.afinidade[modelo]
        w = self.demanda(perfil)
        tem = self.habilidades_de(cursadas)
        aberta = {s: p for s, p in w.items() if s not in tem}

        candidatas = [d["id"] for d in self.disciplinas
                      if d["id"] not in cursadas and d["id"] not in NAO_RECOMENDAVEIS and self.ensina.get(d["id"])]

        def ganho(d: str, abertas: dict) -> tuple[float, float]:
            exp = sum(p for s, p in abertas.items() if s in self.ensina[d])
            lat = sum(p * A[self.idx_d[d], self.idx_s[s]] for s, p in abertas.items() if s not in self.ensina[d] and s in self.idx_s)
            return exp, lat

        trilha, motivos = [], {}
        abertas = dict(aberta)
        while len(trilha) < k:
            restantes = [d for d in candidatas if d not in trilha]
            if not restantes:
                break
            melhor = max(restantes, key=lambda d: (ganho(d, abertas), -self.disciplina[d]["periodo"]))
            if ganho(melhor, abertas)[0] <= 0:
                break
            faltam = [p for p in self._prereqs_faltantes(melhor, set(cursadas) | set(trilha))]
            if len(faltam) + 1 > k - len(trilha):  # a cadeia não cabe na trilha: candidata descartada (RN03)
                candidatas.remove(melhor)
                continue
            for p in faltam:
                if len(trilha) < k and p not in trilha:
                    trilha.append(p)
                    motivos[p] = f"pré-requisito de {titulo_pt(self.disciplina[melhor]['nome'])}"
                    for s in self.ensina.get(p, ()):
                        abertas.pop(s, None)
            if len(trilha) >= k:
                break
            if all(p in trilha or p in cursadas for p in self.requisitos.get(melhor, ())):
                trilha.append(melhor)
                for s in self.ensina[melhor]:
                    abertas.pop(s, None)
            else:  # pré-requisito sem espaço na trilha: não recomendar (RN03)
                candidatas.remove(melhor)

        # A escolha é gulosa (maior ganho primeiro), mas o estudante cursa em outra ordem:
        # exibe pré-requisitos antes e, entre as livres, o período mais cedo do PPC.
        trilha = self._ordem_cursavel(trilha)

        # detalhamento
        cobertas_total = set()
        itens = []
        for pos, d in enumerate(trilha, 1):
            hs = sorted((s for s in self.ensina.get(d, ()) if s in aberta and s not in cobertas_total), key=lambda s: -w.get(s, 0))
            cobertas_total |= set(hs)
            latentes = sorted(((s, float(A[self.idx_d[d], self.idx_s[s]])) for s in aberta
                               if s not in self.ensina.get(d, ()) and s in self.idx_s), key=lambda x: -x[1] * aberta[x[0]])[:3]
            info = self.disciplina[d]
            itens.append({
                "ordem": pos,
                "disciplina": d,
                "nome": titulo_pt(info["nome"]),
                "periodo": info["periodo"],
                "fonte_ementa": info["fonte_ementa"],
                "habilidades_cobertas": [{"id": s, "nome": self.nome_skill(s), "demanda": round(w.get(s, 0.0), 4),
                                          "evidencia": self.evidencias.get((d, s), [])} for s in hs],
                "ganho_aderencia": round(self.aderencia(set(hs), w), 4),
                "afinidades_latentes": [{"id": s, "nome": self.nome_skill(s), "afinidade": round(a, 4)} for s, a in latentes],
                "motivo": motivos.get(d) or (f"ensina {len(hs)} competência{'s' if len(hs) > 1 else ''} que as vagas pedem "
                                             f"e você ainda não tem" if hs else "completa a sequência da trilha"),
                "pre_requisitos": sorted(self.requisitos.get(d, ())),
            })

        depois = tem | cobertas_total
        nao_ensinadas = sorted((s for s in aberta if s not in self.ensinadas), key=lambda s: -aberta[s])
        complementares = [{"id": s, "nome": self.nome_skill(s), "demanda": round(aberta[s], 4),
                           "categoria": self.ont.categorias[self.ont.habilidades[s].categoria],
                           "disciplina_base": self.apoio_estrutural(s)} for s in nao_ensinadas[:12]]
        vs = self.vagas_do_perfil(perfil)
        return {
            "perfil": perfil or "todos",
            "perfil_nome": NOMES_PERFIS.get(perfil, "Todas as vagas de TI"),
            "vagas_consideradas": len(vs),
            "modelo_afinidade": modelo,
            "k": k,
            "disciplinas_cursadas": len(cursadas),
            "habilidades_atuais": sorted(tem),
            "aderencia_antes": round(self.aderencia(tem, w), 4),
            "aderencia_depois": round(self.aderencia(depois, w), 4),
            "aderencia_teto_curricular": round(self.aderencia(self.ensinadas, w), 4),
            "trilha": itens,
            "lacunas_abertas": [{"id": s, "nome": self.nome_skill(s), "demanda": round(p, 4),
                                 "ensinada_no_ppc": s in self.ensinadas}
                                for s, p in sorted(aberta.items(), key=lambda x: -x[1]) if s not in depois][:20],
            "habilidades_complementares": complementares,
            "observacao": "Nenhum dado informado é armazenado: o cálculo é feito em memória e descartado ao fim da requisição.",
        }

    @cached_property
    def coocorrencia(self) -> Counter:
        """Número de vagas em que cada par ordenado de habilidades aparece junto."""
        c = Counter()
        for v in self.vagas:
            hs = sorted(set(v["habilidades"]))
            for a in hs:
                for b in hs:
                    if a != b:
                        c[(a, b)] += 1
        return c

    def pontes(self, s: str, d: str) -> list[dict]:
        """Habilidades ensinadas por d que as vagas pedem junto com s (evidência de mercado)."""
        minimo = carregar_config()["grafo"]["coocorrencia_minima"]
        ps = [(h, self.coocorrencia[(s, h)]) for h in self.ensina.get(d, ()) if self.coocorrencia[(s, h)] >= minimo]
        return [{"id": h, "nome": self.nome_skill(h), "vagas": n} for h, n in sorted(ps, key=lambda x: (-x[1], x[0]))]

    def apoio_estrutural(self, s: str) -> dict | None:
        """Disciplina de apoio para uma habilidade que o PPC não ensina.

        Usa sempre a GNN: para habilidades sem nenhuma evidência textual nas
        ementas o TF-IDF é nulo por construção, e só a estrutura do grafo
        produz sinal. Para não exibir associações espúrias, a sugestão precisa
        ser corroborada pelo mercado: a disciplina tem de ensinar ao menos uma
        habilidade que as vagas pedem junto com a lacuna (coocorrência mínima
        do grafo), e a afinidade da GNN tem de superar o limiar configurado.
        Entre as candidatas, vence a de maior afinidade. As sugestões não foram
        validadas por especialistas e são apresentadas como tal, com a
        habilidade-ponte como justificativa.
        """
        j = self.idx_s.get(s)
        if j is None:
            return None
        minimo = carregar_config()["recomendacao"].get("afinidade_minima_apoio", 0.15)
        col = self.afinidade["gnn"][:, j]
        candidatas = [(float(col[i]), d) for i, d in enumerate(self.ids_d)
                      if d not in NAO_RECOMENDAVEIS and self.ensina_tecnica(d) and self.pontes(s, d)]
        if not candidatas:
            return None
        afin, d = max(candidatas)
        if afin < minimo:
            return None
        return {"disciplina": d, "nome": titulo_pt(self.disciplina[d]["nome"]), "afinidade": round(afin, 4),
                "modelo": "gnn", "validada": False, "ponte": self.pontes(s, d)[:2]}

    def _ordem_cursavel(self, trilha: list[str]) -> list[str]:
        """Ordena a trilha como pode ser cursada: pré-requisitos antes, depois pelo período do PPC;
        no empate, mantém a ordem de escolha (a de maior ganho primeiro)."""
        escolha = {d: i for i, d in enumerate(trilha)}
        restantes, ordem = set(trilha), []
        while restantes:
            livres = [d for d in restantes if not (self.requisitos.get(d, set()) & restantes)]
            d = min(livres, key=lambda x: (self.disciplina[x]["periodo"], escolha[x]))
            ordem.append(d)
            restantes.remove(d)
        return ordem

    def _prereqs_faltantes(self, d: str, disponiveis: set) -> list[str]:
        """Pré-requisitos ainda não cumpridos, em ordem topológica (os mais básicos primeiro)."""
        ordem, visit = [], set()

        def dfs(x):
            for p in sorted(self.requisitos.get(x, ())):
                if p in disponiveis or p in visit:
                    continue
                visit.add(p)
                dfs(p)
                ordem.append(p)

        dfs(d)
        return ordem

    # ------------------------------------------------------------- RF26
    def afinidade_disciplinas(self, habilidades: list[str], modelo: str | None = None, top: int = 10) -> dict:
        desconhecidas = [s for s in habilidades if s not in self.idx_s]
        if desconhecidas or not habilidades:
            raise ErroEntrada(f"habilidades inválidas: {', '.join(desconhecidas) or '(vazio)'}")
        modelo = self.modelo(modelo)
        A = self.afinidade[modelo]
        cols = [self.idx_s[s] for s in habilidades]
        esc = A[:, cols].mean(1)
        # Estágio, TCC e optativa não têm conteúdo fixo a recomendar, como na trilha (RF29).
        validos = [i for i, d in enumerate(self.ids_d) if d not in NAO_RECOMENDAVEIS]
        ordem = sorted(validos, key=lambda i: (-esc[i], i))[:top]
        return {"modelo_afinidade": modelo, "habilidades": habilidades, "disciplinas": [
            {"disciplina": self.ids_d[i], "nome": titulo_pt(self.disciplina[self.ids_d[i]]["nome"]),
             "periodo": self.disciplina[self.ids_d[i]]["periodo"], "afinidade": round(float(esc[i]), 4),
             "ensina_explicitamente": sorted(set(habilidades) & self.ensina.get(self.ids_d[i], set()))}
            for i in ordem]}

    # ------------------------------------------------------------- RF32–RF34
    def diagnostico(self, perfil: str | None = None, modelo: str | None = None) -> dict:
        modelo = self.modelo(modelo)
        A = self.afinidade[modelo]
        w = self.demanda(perfil)
        vs = self.vagas_do_perfil(perfil)
        n = len(vs)
        lacunas = []
        for s, p in sorted(w.items(), key=lambda x: -x[1]):
            if s in self.ensinadas:
                continue
            apoio = self.apoio_estrutural(s)
            lacunas.append({"id": s, "nome": self.nome_skill(s), "categoria": self.ont.categorias[self.ont.habilidades[s].categoria],
                            "vagas": int(round(p * n)), "demanda": round(p, 4),
                            "disciplina_mais_proxima": apoio["nome"] if apoio else None,
                            "afinidade": apoio["afinidade"] if apoio else None,
                            "ponte": apoio["ponte"] if apoio else []})
        cobertas = sorted(((s, p) for s, p in w.items() if s in self.ensinadas), key=lambda x: -x[1])
        sem_demanda = sorted(s for s in self.ensinadas if w.get(s, 0) == 0)
        por_cat = defaultdict(lambda: {"demandadas": 0, "cobertas": 0})
        for s in w:
            c = self.ont.categorias[self.ont.habilidades[s].categoria]
            por_cat[c]["demandadas"] += 1
            por_cat[c]["cobertas"] += int(s in self.ensinadas)
        return {
            "perfil": perfil or "todos", "perfil_nome": NOMES_PERFIS.get(perfil, "Todas as vagas de TI"),
            "vagas_consideradas": n, "modelo_afinidade": modelo,
            "cobertura_da_demanda": round(self.aderencia(self.ensinadas, w), 4),
            "habilidades_demandadas": len(w), "habilidades_cobertas": len(cobertas),
            "lacunas": lacunas,
            "cobertas": [{"id": s, "nome": self.nome_skill(s), "demanda": round(p, 4),
                          "disciplinas": sorted(titulo_pt(self.disciplina[d]["nome"]) for d, hs in self.ensina.items() if s in hs)}
                         for s, p in cobertas],
            "ensinadas_sem_demanda": [{"id": s, "nome": self.nome_skill(s)} for s in sem_demanda],
            "por_categoria": [{"categoria": c, **v} for c, v in sorted(por_cat.items(), key=lambda x: -x[1]["demandadas"])],
        }

    def diagnostico_csv(self, perfil: str | None = None, modelo: str | None = None) -> str:  # RF35
        d = self.diagnostico(perfil, modelo)
        buf = io.StringIO()
        wr = csv.writer(buf, delimiter=";")
        wr.writerow(["situacao", "habilidade", "categoria", "vagas_que_exigem", "percentual_das_vagas", "disciplina_mais_proxima",
                     "afinidade", "evidencia_de_mercado"])
        for x in d["lacunas"]:
            evid = " | ".join(f"pedida junto com {p['nome']} em {p['vagas']} vagas" for p in x["ponte"])
            wr.writerow(["lacuna", x["nome"], x["categoria"], x["vagas"], f"{100 * x['demanda']:.1f}".replace(".", ","),
                         x["disciplina_mais_proxima"] or "", f"{x['afinidade']:.3f}".replace(".", ",") if x["afinidade"] else "", evid])
        for x in d["cobertas"]:
            wr.writerow(["coberta", x["nome"], "", round(x["demanda"] * d["vagas_consideradas"]),
                         f"{100 * x['demanda']:.1f}".replace(".", ","), " | ".join(x["disciplinas"]), "", ""])
        for x in d["ensinadas_sem_demanda"]:
            wr.writerow(["ensinada_sem_demanda", x["nome"], "", 0, "0,0", "", "", ""])
        return "﻿" + buf.getvalue()  # BOM: abre com acentos corretos no Excel

    # ------------------------------------------------------------- mercado
    def mercado(self, perfil: str | None = None, top: int = 15) -> dict:
        w = self.demanda(perfil)
        vs = self.vagas_do_perfil(perfil)
        return {
            "perfil": perfil or "todos", "vagas": len(vs),
            "por_perfil": [{"id": p, "nome": n, "vagas": sum(1 for v in self.vagas if v["perfil"] == p)} for p, n in NOMES_PERFIS.items()],
            "habilidades_mais_demandadas": [{"id": s, "nome": self.nome_skill(s), "demanda": round(p, 4),
                                             "vagas": int(round(p * len(vs))), "ensinada_no_ppc": s in self.ensinadas}
                                            for s, p in sorted(w.items(), key=lambda x: -x[1])[:top]],
        }
