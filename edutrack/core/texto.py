"""Utilidades de texto em português."""
from __future__ import annotations

import re

_MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "as", "os", "para", "com", "por", "no", "na", "nos", "nas"}
_ROMANOS = re.compile(r"^(i{1,3}|iv|v|vi{1,3}|ix|x)$", re.IGNORECASE)


def titulo_pt(nome: str) -> str:
    """Caixa de título em português: preposições e conjunções em minúscula,
    algarismos romanos em maiúscula ("ALGORITMO E ESTRUTURA DE DADOS II" ->
    "Algoritmo e Estrutura de Dados II")."""
    palavras = re.split(r"(\s+|-)", (nome or "").strip().lower())
    out, primeira = [], True
    for p in palavras:
        if not p or p.isspace() or p == "-":
            out.append(p)
            continue
        if _ROMANOS.match(p) and not primeira:
            out.append(p.upper())
        elif p in _MINUSCULAS and not primeira:
            out.append(p)
        else:
            out.append(p[:1].upper() + p[1:])
        primeira = False
    return "".join(out)
