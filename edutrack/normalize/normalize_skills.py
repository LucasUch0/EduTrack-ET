"""Normalização semântica de habilidades (RF11–RF16).

Duas camadas de decisão, nesta ordem:

1. **Exata** — o texto é varrido contra o termo canônico e todos os sinônimos da
   ontologia (sem acento, sem distinção de maiúsculas). Vence a ocorrência mais
   longa, para que "Power BI" não vire "BI" e "JavaScript" não vire "Java".
   Siglas ambíguas em português (IA, MES, AD...) ficam em ``aliases_cs`` e só
   casam com a grafia em maiúsculas.
2. **Aproximada (fuzzy)** — termos candidatos que sobraram (itens de ementa,
   siglas, nomes de tecnologia) são comparados aos sinônimos. Um par é aceito
   em dois casos: (a) a *forma compacta* (sem espaços, hífens e pontos) é
   idêntica — "SpringBoot" = "Spring Boot", "Power Shell" = "PowerShell";
   (b) os termos de conteúdo se alinham um a um, diferindo só por flexão de
   gênero/número ("Diagramas de atividade" = "diagrama de atividade"), e a
   razão de similaridade de ``difflib.SequenceMatcher`` entre as frases é
   >= limiar (padrão 0,87, RF13). Sem alinhamento, o termo vai para a
   quarentena (RN01). O alinhamento por termo foi introduzido porque a razão
   de caracteres isolada aceitava pares como "Formação" ~ "formatação" (0,89)
   e "Supervisor" ~ "supervisório" (0,91) — ver docs/VALIDACAO_FUZZY.md.

Cada decisão gera uma linha de auditoria com termo original, canônico, camada
e escore (RF14). Termos não resolvidos são agregados por frequência para
curadoria (RF15). Nada aqui depende de bibliotecas externas: o resultado é o
mesmo em qualquer máquina (RNF26).

Complexidade: a camada exata é uma única varredura com expressão regular
compilada, O(n) no tamanho do texto para um conjunto fixo de sinônimos; a camada
aproximada consulta um dicionário de formas compactas (O(1)) e um índice por
(nº de termos, prefixo de 4 letras), de modo que cada candidato é comparado só
com os poucos sinônimos do mesmo bloco — O(c * b * L^2), com b pequeno.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Normalização de texto com preservação de posições
# ---------------------------------------------------------------------------
_HIFENS = {"-", "‐", "‑", "‒", "–", "—", "_"}


def _char_base(c: str) -> str:
    """Remove o acento de um caractere mantendo exatamente 1 caractere."""
    if c in _HIFENS:
        return " "
    d = unicodedata.normalize("NFD", c)
    base = d[0] if d else c
    return base if len(base) == 1 else c


def norm_preservando(texto: str, minusculas: bool = True) -> str:
    """Normaliza caractere a caractere: o índice i do resultado corresponde ao
    índice i do texto original, o que permite recuperar o termo original
    exatamente como apareceu (trilha de auditoria, RF14)."""
    out = "".join(_char_base(c) for c in texto)
    return out.lower() if minusculas else out


def norm_termo(termo: str) -> str:
    """Normalização compacta para comparar termos isolados."""
    t = norm_preservando(termo).strip()
    t = re.sub(r"\s+", " ", t)
    return t


_VERSAO = re.compile(r"(\s+v?\d+(\.\d+)*[a-z]?)+$")
_STOP = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "as", "os", "para", "com", "no", "na",
         "nos", "nas", "por", "ao", "aos", "um", "uma", "ou", "the", "of", "and", "to", "in"}


def sem_versao(termo: str) -> str:
    """"angular 20" -> "angular"; "python 3.11" -> "python"."""
    return _VERSAO.sub("", termo).strip()


def compacta(termo: str) -> str:
    """Forma compacta: sem espaços, hífens, pontos e barras ("spring boot" -> "springboot")."""
    return re.sub(r"[^a-z0-9#+]+", "", termo)


def termos_conteudo(termo: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9#+]+", termo) if t and t not in _STOP]


def variacao_morfologica(a: str, b: str) -> bool:
    """True se ``a`` e ``b`` diferem apenas por flexão de gênero/número no final
    (até 2 letras entre a, o, e, s), com radical comum de pelo menos 4 letras:
    "eletronico" ~ "eletronica", "diagramas" ~ "diagrama"; mas não
    "supervisor" ~ "supervisorio" nem "formacao" ~ "formatacao"."""
    if a == b:
        return True
    p = os.path.commonprefix([a, b])
    ra, rb = a[len(p):], b[len(p):]
    return len(p) >= 4 and len(ra) <= 2 and len(rb) <= 2 and set(ra + rb) <= set("aoes")


def contexto_maiusculo(texto: str, inicio: int, fim: int) -> bool:
    """True se a linha em que a ocorrência está é escrita quase toda em
    maiúsculas (títulos de vaga). Nesse contexto uma sigla em maiúsculas não
    carrega informação: "OP DE MÁQUINA IA" não é Inteligência Artificial."""
    a = texto.rfind("\n", 0, inicio) + 1
    b = texto.find("\n", fim)
    linha = texto[a: b if b >= 0 else len(texto)]
    letras = [c for c in linha if c.isalpha()]
    if len(letras) < 8:
        return False
    return sum(c.isupper() for c in letras) / len(letras) >= 0.6


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------
@dataclass
class Ocorrencia:
    doc_id: str
    termo_original: str
    skill_id: str | None
    camada: str  # "exata", "fuzzy", "nao_resolvido"
    escore: float
    inicio: int = -1
    fim: int = -1
    sinonimo: str = ""


@dataclass
class Habilidade:
    id: str
    nome: str
    categoria: str
    aliases: list
    aliases_cs: list


class Ontologia:
    def __init__(self, caminho: str | Path):
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        self.meta = {k: v for k, v in dados.items() if k not in ("habilidades",)}
        self.categorias = {c["id"]: c["nome"] for c in dados["categorias"]}
        self.habilidades: dict[str, Habilidade] = {}
        for h in dados["habilidades"]:
            self.habilidades[h["id"]] = Habilidade(
                id=h["id"], nome=h["nome"], categoria=h["categoria"],
                aliases=list(h.get("aliases", [])), aliases_cs=list(h.get("aliases_cs", [])),
            )
        self.bloqueios = [norm_termo(b) for b in dados.get("bloqueios", [])]
        self._validar()

    def _validar(self) -> None:
        cats = set(self.categorias)
        for h in self.habilidades.values():
            if h.categoria not in cats:
                raise ValueError(f"Habilidade {h.id} com categoria desconhecida {h.categoria}")

    @property
    def ids(self) -> list[str]:
        return list(self.habilidades)

    def sinonimos(self) -> dict[str, str]:
        """Mapa sinônimo normalizado -> id canônico (inclui o nome e o id)."""
        mapa: dict[str, str] = {}
        for h in self.habilidades.values():
            for s in [h.nome] + h.aliases:
                k = norm_termo(s)
                if k and k not in mapa:
                    mapa[k] = h.id
        return mapa


# ---------------------------------------------------------------------------
# Normalizador
# ---------------------------------------------------------------------------
_PREFIXOS_CANDIDATO = re.compile(
    r"^(e\s+)?(conhecimentos?|experiencias?|dominio|nocoes|vivencia|familiaridade|"
    r"desejavel|diferencial|diferenciais|requisitos?|habilidades?|atuacao|"
    r"conhecimento (basico|intermediario|avancado|solido|pratico)|"
    r"experiencia (com|em|no|na|nos|nas))\s*(com|em|de|no|na|nos|nas|sobre|:)?\s+",
)

# Siglas que aparecem em vagas mas não são habilidades (RF15 ficaria poluído)
_SIGLAS_NAO_TECNICAS = {
    "CLT", "PJ", "RH", "PCD", "PCDS", "VR", "VT", "VA", "AM", "BR", "CNH", "CPF", "CEP", "EPI", "EPIS",
    "NR", "NRS", "PCP", "DP", "CNPJ", "CV", "LTDA", "SA", "ME", "MEI", "OAB", "SP", "RJ", "MG", "PR",
    "RS", "SC", "PA", "RR", "AC", "RO", "AP", "TO", "MA", "CE", "PE", "BA", "GO", "MT", "MS", "DF",
    "ES", "PI", "RN", "PB", "SE", "AL", "PLR", "PPR", "TI", "T.I", "JR", "SR", "PL", "II", "III", "IV",
    "IPTU", "INSS", "FGTS", "SESMT", "CIPA", "HDA", "EAD", "MBA", "UFAM", "UEA", "IFAM", "ZFM", "PIM",
    "SUFRAMA", "LGBTQIA", "LGBT", "LGBTI", "OK", "SMS", "WHATSAPP", "CEO", "CTO", "CFO", "HR", "USD", "BRL",
    "OU", "IT", "TIC", "TV", "MEC", "SESC", "SENAI", "SESI", "PAY", "NIL", "COE", "EJ", "AZ", "GHZ", "MHZ",
    "OS", "SOWS", "SOW", "ISO", "NBR", "CREA", "CFT", "CFTV", "PCM", "QA/QC", "DE", "EM", "DA", "DO", "PARA",
}
_TOKEN_TECNICO = re.compile(
    r"(?<![\w.#+])("
    r"[A-Z]{2,5}[0-9#+]*"                  # siglas curtas: SQL, AWS, CLP, ITIL
    r"|[A-Za-z]+[#+]{1,2}"                 # C#, C++
    r"|\.[A-Za-z]{2,}"                     # .NET
    r"|[A-Za-z]+\.[jJ][sS]"                # Node.js, Vue.js
    r"|[A-Za-z]*[a-z][A-Z][A-Za-z0-9]*"    # PostgreSQL, TypeScript, GitHub
    r"|[A-Za-z]+\d+[A-Za-z0-9]*"           # ESP32, S3, Html5
    r")(?![\w#+])"
)


class Normalizador:
    def __init__(self, ontologia: Ontologia, limiar: float = 0.87, tamanho_minimo_fuzzy: int = 5):
        self.ont = ontologia
        self.limiar = float(limiar)
        self.tam_min = int(tamanho_minimo_fuzzy)
        self._mapa = ontologia.sinonimos()
        self._re_ci = self._compilar(self._mapa.keys())
        mapa_cs = {}
        for h in ontologia.habilidades.values():
            for s in h.aliases_cs:
                mapa_cs[norm_preservando(s, minusculas=False).strip()] = h.id
        self._mapa_cs = mapa_cs
        self._re_cs = self._compilar(mapa_cs.keys()) if mapa_cs else None
        self._re_bloq = self._compilar(ontologia.bloqueios) if ontologia.bloqueios else None
        # índices da camada aproximada
        self._compactos: dict[str, str] = {}
        self._blocos: dict[tuple[int, str], list[str]] = {}
        for s in self._mapa:
            if len(s) < self.tam_min:
                continue
            self._compactos.setdefault(compacta(s), s)
            tc = termos_conteudo(s)
            if tc:
                self._blocos.setdefault((len(tc), tc[0][:4]), []).append(s)

    @staticmethod
    def _compilar(termos: Iterable[str]) -> re.Pattern:
        partes = []
        for t in sorted(set(termos), key=len, reverse=True):
            if not t:
                continue
            p = re.escape(t).replace(r"\ ", r"\s+")
            partes.append(p)
        padrao = r"(?<![a-z0-9A-Z])(" + "|".join(partes) + r")(?![a-z0-9A-Z#+])"
        return re.compile(padrao)

    # -- camada 1 ----------------------------------------------------------
    def _exatas(self, texto: str, doc_id: str) -> list[Ocorrencia]:
        ocupado = bytearray(len(texto))
        res: list[Ocorrencia] = []
        base_ci = norm_preservando(texto, minusculas=True)
        if self._re_bloq is not None:
            for m in self._re_bloq.finditer(base_ci):
                ocupado[m.start():m.end()] = b"\x01" * (m.end() - m.start())
        for m in self._re_ci.finditer(base_ci):
            if any(ocupado[m.start():m.end()]):
                continue
            chave = re.sub(r"\s+", " ", m.group(1))
            sid = self._mapa.get(chave)
            if sid is None:
                continue
            ocupado[m.start():m.end()] = b"\x01" * (m.end() - m.start())
            res.append(Ocorrencia(doc_id, texto[m.start():m.end()], sid, "exata", 1.0, m.start(), m.end(), chave))
        if self._re_cs is not None:
            base_cs = norm_preservando(texto, minusculas=False)
            for m in self._re_cs.finditer(base_cs):
                if any(ocupado[m.start():m.end()]):
                    continue
                sid = self._mapa_cs.get(m.group(1))
                if sid is None or contexto_maiusculo(texto, m.start(), m.end()):
                    continue
                ocupado[m.start():m.end()] = b"\x01" * (m.end() - m.start())
                res.append(Ocorrencia(doc_id, texto[m.start():m.end()], sid, "exata", 1.0, m.start(), m.end(), m.group(1)))
        res.sort(key=lambda o: o.inicio)
        self._ocupado = ocupado
        return res

    # -- candidatos para a camada 2 e para o relatório de não resolvidos -----
    @staticmethod
    def candidatos(texto: str, modo: str = "vaga", excluir: Iterable[str] = ()) -> list[tuple[str, int, int]]:
        """Extrai termos candidatos com suas posições.

        * Em ementas (``modo='ementa'``) os itens são sintagmas separados por
          ponto, ponto e vírgula ou dois-pontos — cada item é um candidato.
        * Em vagas, além de itens curtos de listas, entram tokens com forma de
          tecnologia (siglas, nomes com maiúsculas internas, versões, C#, .NET).
          Siglas em linhas escritas todas em maiúsculas e palavras do nome da
          empresa (``excluir``) não são candidatas.
        """
        excluir_n = {norm_termo(e) for e in excluir if e}
        cands: list[tuple[str, int, int]] = []
        sep = re.compile(r"[\n;:•·|()\[\]]|(?<!\w)\.(?!\w)|\.(?=\s|$)|,(?!\d)")
        pos = 0
        segmentos = []
        for m in sep.finditer(texto + "\n"):
            segmentos.append((pos, m.start()))
            pos = m.end()
        max_pal = 6 if modo == "ementa" else 4
        for a, b in segmentos:
            seg = texto[a:b]
            if not seg.strip():
                continue
            lead = len(seg) - len(seg.lstrip())
            s = seg.strip().rstrip(".")
            a2 = a + lead
            # remove prefixos do tipo "experiência com" / "conhecimento em"
            sn = norm_preservando(s)
            mp = _PREFIXOS_CANDIDATO.match(sn)
            if mp:
                s = s[mp.end():]
                a2 += mp.end()
            s = s.strip(" -\t*–")
            if not s:
                continue
            npal = len(s.split())
            if 1 <= npal <= max_pal and len(s) >= 2 and not re.fullmatch(r"[\d\s.,%/-]+", s):
                ini = texto.find(s, a2, b + 1)
                ini = ini if ini >= 0 else a2
                cands.append((s, ini, ini + len(s)))
        for m in _TOKEN_TECNICO.finditer(texto):
            tok = m.group(1)
            if tok.upper().strip(".") in _SIGLAS_NAO_TECNICAS or norm_termo(tok) in excluir_n:
                continue
            if tok.isupper() and contexto_maiusculo(texto, m.start(), m.end()):
                continue
            cands.append((tok, m.start(), m.end()))
        cands = [c for c in cands if norm_termo(c[0]) not in excluir_n and re.search(r"[A-Za-zÀ-ú]{2}", c[0])]
        # dedup por posição
        vistos, unicos = set(), []
        for c in cands:
            if (c[1], c[2]) not in vistos:
                vistos.add((c[1], c[2]))
                unicos.append(c)
        return unicos

    # -- camada 2 ----------------------------------------------------------
    def normalizar_termo(self, termo: str) -> tuple[str | None, str, float, str]:
        """Resolve um termo isolado: (skill_id | None, camada, escore, sinônimo)."""
        t = sem_versao(norm_termo(termo))
        if not t:
            return None, "nao_resolvido", 0.0, ""
        if t in self._mapa:
            return self._mapa[t], "exata", 1.0, t
        cs = norm_preservando(termo, minusculas=False).strip()
        if cs in self._mapa_cs:
            return self._mapa_cs[cs], "exata", 1.0, cs
        if len(t) < self.tam_min:
            return None, "nao_resolvido", 0.0, ""
        # (a) forma compacta idêntica
        c = compacta(t)
        if c in self._compactos:
            alvo = self._compactos[c]
            return self._mapa[alvo], "fuzzy", 1.0, alvo
        # (b) alinhamento termo a termo (flexão) + razão de similaridade >= limiar
        tc = termos_conteudo(t)
        melhor, alvo = 0.0, ""
        if tc:
            for s in self._blocos.get((len(tc), tc[0][:4]), []):
                sc = termos_conteudo(s)
                if not all(variacao_morfologica(x, y) for x, y in zip(tc, sc)):
                    continue
                r = SequenceMatcher(None, t, s, autojunk=False).ratio()
                if r > melhor:
                    melhor, alvo = r, s
        if alvo and melhor >= self.limiar:
            return self._mapa[alvo], "fuzzy", round(melhor, 4), alvo
        return None, "nao_resolvido", round(melhor, 4), alvo

    def similaridade_bruta(self, termo: str, k: int = 1) -> list[tuple[str, float]]:
        """Os k sinônimos mais parecidos pela razão de caracteres pura, sem o
        alinhamento por termo. Usado apenas para montar a amostra de validação
        da camada aproximada (RNF19)."""
        t = sem_versao(norm_termo(termo))
        pares = []
        for s in self._mapa:
            if len(s) < self.tam_min:
                continue
            sm = SequenceMatcher(None, t, s, autojunk=False)
            if sm.real_quick_ratio() < 0.75 or sm.quick_ratio() < 0.75:
                continue
            pares.append((s, sm.ratio()))
        pares.sort(key=lambda x: -x[1])
        return pares[:k]

    def extrair(self, texto: str, doc_id: str = "", modo: str = "vaga", excluir: Iterable[str] = ()) -> list[Ocorrencia]:
        """Aplica as duas camadas a um texto e devolve todas as decisões."""
        texto = texto or ""
        ocorr = self._exatas(texto, doc_id)
        ocupado = self._ocupado
        for termo, a, b in self.candidatos(texto, modo=modo, excluir=excluir):
            if a < 0 or b > len(texto) or any(ocupado[a:b]):
                continue  # já resolvido na camada exata
            sid, camada, escore, alvo = self.normalizar_termo(termo)
            if sid is not None:
                ocupado[a:b] = b"\x01" * (b - a)
            ocorr.append(Ocorrencia(doc_id, termo, sid, camada, escore, a, b, alvo))
        ocorr.sort(key=lambda o: (o.inicio, o.fim))
        return ocorr

    def habilidades_de(self, texto: str, doc_id: str = "", modo: str = "vaga") -> tuple[set[str], list[Ocorrencia]]:
        oc = self.extrair(texto, doc_id, modo)
        return {o.skill_id for o in oc if o.skill_id}, oc

    def mascarar(self, texto: str, evidencias: Iterable[tuple[int, int]]) -> str:
        """Remove do texto os trechos indicados (substituídos por espaços,
        preservando posições). Usado no cenário de avaliação com evidência
        textual mascarada."""
        chars = list(texto)
        for a, b in evidencias:
            for i in range(max(a, 0), min(b, len(chars))):
                chars[i] = " "
        return "".join(chars)


# ---------------------------------------------------------------------------
# Relatórios
# ---------------------------------------------------------------------------
def termo_tecnico(termo: str) -> bool:
    """Heurística usada só para o indicador de cobertura (RNF18): considera
    técnico um candidato com forma de tecnologia (sigla, maiúscula interna,
    dígito, C#/.NET)."""
    return bool(_TOKEN_TECNICO.fullmatch(termo.strip()))


def relatorio_nao_resolvidos(ocorrencias: Iterable[Ocorrencia]) -> list[tuple[str, int]]:
    """Termos em quarentena ordenados por frequência (RF15)."""
    c = Counter(norm_termo(o.termo_original) for o in ocorrencias if o.skill_id is None)
    return c.most_common()


def cobertura(ocorrencias: Iterable[Ocorrencia], freq_minima: int = 2) -> dict:
    """Cobertura de normalização (RNF18) entre termos técnicos candidatos com
    frequência >= freq_minima: fração resolvida para algum canônico."""
    tot, res = Counter(), Counter()
    for o in ocorrencias:
        if not termo_tecnico(o.termo_original):
            continue
        k = norm_termo(o.termo_original)
        tot[k] += 1
        if o.skill_id:
            res[k] += 1
    elegiveis = [k for k, n in tot.items() if n >= freq_minima]
    resolvidos = [k for k in elegiveis if res[k] > 0]
    return {
        "freq_minima": freq_minima,
        "termos_elegiveis": len(elegiveis),
        "termos_resolvidos": len(resolvidos),
        "cobertura": round(len(resolvidos) / len(elegiveis), 4) if elegiveis else None,
        "nao_resolvidos_elegiveis": sorted(set(elegiveis) - set(resolvidos)),
    }


def ocorrencias_para_linhas(ocorrencias: Iterable[Ocorrencia], tipo_doc: str) -> list[dict]:
    linhas = []
    for o in ocorrencias:
        d = asdict(o)
        d["tipo_documento"] = tipo_doc
        linhas.append(d)
    return linhas
