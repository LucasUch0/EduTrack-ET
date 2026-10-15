"""Esquemas de entrada e saída da API (validação e documentação OpenAPI)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Perfil = Optional[Literal["todos", "desenvolvimento", "dados_ia", "infraestrutura", "industria", "corporativo"]]
Modelo = Optional[Literal["auto", "tfidf", "gnn"]]


class TrilhaEntrada(BaseModel):
    """Seleção do estudante. Nada aqui é armazenado (RF42, RN07)."""

    cursadas: list[str] = Field(default_factory=list, max_length=60,
                                description="Identificadores das disciplinas já cursadas (ver /api/disciplinas).",
                                examples=[["aed1", "aed2", "programacao_oo", "sistemas_operacionais"]])
    perfil: Perfil = Field(None, description="Restringe o mercado a um perfil de vaga (RF31).")
    k: int = Field(5, ge=1, le=10, description="Tamanho da trilha (RN05: padrão 5).")
    modelo: Modelo = Field("auto", description="Modelo de afinidade; 'auto' usa o melhor da avaliação.")


class HabilidadeCoberta(BaseModel):
    id: str
    nome: str
    demanda: float
    evidencia: list[str] = []


class Afinidade(BaseModel):
    id: str
    nome: str
    afinidade: float


class ItemTrilha(BaseModel):
    ordem: int
    disciplina: str
    nome: str
    periodo: int
    fonte_ementa: str
    habilidades_cobertas: list[HabilidadeCoberta]
    ganho_aderencia: float
    afinidades_latentes: list[Afinidade]
    motivo: str
    pre_requisitos: list[str]


class Ponte(BaseModel):
    """Habilidade ensinada pela disciplina de apoio que as vagas pedem junto com a lacuna."""
    id: str
    nome: str
    vagas: int


class Apoio(BaseModel):
    disciplina: str
    nome: str
    afinidade: float
    modelo: str
    validada: bool
    ponte: list[Ponte] = []


class Complementar(BaseModel):
    id: str
    nome: str
    demanda: float
    categoria: str
    disciplina_base: Optional[Apoio] = None


class Lacuna(BaseModel):
    id: str
    nome: str
    demanda: float
    ensinada_no_ppc: bool


class TrilhaSaida(BaseModel):
    perfil: str
    perfil_nome: str
    vagas_consideradas: int
    modelo_afinidade: str
    k: int
    disciplinas_cursadas: int
    habilidades_atuais: list[str]
    aderencia_antes: float
    aderencia_depois: float
    aderencia_teto_curricular: float
    trilha: list[ItemTrilha]
    lacunas_abertas: list[Lacuna]
    habilidades_complementares: list[Complementar]
    observacao: str
