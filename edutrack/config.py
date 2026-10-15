"""Leitura centralizada de config.yaml (RNF25)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def carregar_config(caminho: str | None = None) -> dict:
    p = Path(caminho or os.environ.get("EDUTRACK_CONFIG", RAIZ / "config.yaml"))
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def caminho(chave: str) -> Path:
    """Resolve um caminho de config.yaml relativo à raiz do projeto."""
    rel = carregar_config()["caminhos"][chave]
    return (RAIZ / rel).resolve()


def processados() -> Path:
    p = caminho("processados")
    p.mkdir(parents=True, exist_ok=True)
    return p


def artefatos() -> Path:
    p = caminho("artefatos")
    p.mkdir(parents=True, exist_ok=True)
    return p
