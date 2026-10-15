"""Instrumentação de energia e emissões (RF44, RNF06).

Estimativa pela metodologia Green Algorithms (Lannelongue; Grealey; Inouye,
2021): energia = tempo x (potência dos núcleos x uso + potência da memória) x
PUE. O uso de CPU é medido pelo tempo de processador do próprio processo
(``time.process_time``), o que dispensa bibliotecas externas e funciona em
Windows, Linux e macOS. A emissão aplica o fator médio do Sistema Interligado
Nacional (MCTI). Se o CodeCarbon estiver instalado, use-o para comparação; os
valores aqui são estimativas documentadas, não medições de tomada.
"""
from __future__ import annotations

import json
import os
import platform
import time
from dataclasses import asdict, dataclass

from edutrack.config import artefatos, carregar_config

POTENCIA_MEMORIA_W_POR_GB = 0.3725  # Green Algorithms


@dataclass
class Medicao:
    etapa: str
    duracao_s: float
    cpu_s: float
    nucleos_logicos: int
    uso_medio_cpu: float
    energia_kwh: float
    co2_g: float
    potencia_nucleo_w: float
    fator_kgco2_kwh: float
    plataforma: str


class RastreadorEnergia:
    """Uso: ``with RastreadorEnergia("treino") as r: ...`` ; depois ``r.medicao``."""

    def __init__(self, etapa: str, memoria_gb: float = 1.0):
        cfg = carregar_config()["energia"]
        self.etapa = etapa
        self.p_nucleo = float(cfg["potencia_cpu_por_nucleo_w"])
        self.fator = float(cfg["fator_emissao_kgco2_kwh"])
        self.mem = memoria_gb
        self.medicao: Medicao | None = None

    def __enter__(self):
        self.t0 = time.perf_counter()
        self.c0 = time.process_time()
        return self

    def __exit__(self, *exc):
        dt = max(time.perf_counter() - self.t0, 1e-9)
        dc = max(time.process_time() - self.c0, 0.0)
        n = os.cpu_count() or 1
        uso = min(dc / (dt * n), 1.0)
        # energia (kWh) = horas x (núcleos x W/núcleo x uso + GB x W/GB) / 1000 ; PUE = 1 (computador pessoal)
        e = (dt / 3600.0) * (n * self.p_nucleo * uso + self.mem * POTENCIA_MEMORIA_W_POR_GB) / 1000.0
        self.medicao = Medicao(self.etapa, round(dt, 4), round(dc, 4), n, round(uso, 4), e, e * self.fator * 1000.0,
                               self.p_nucleo, self.fator, f"{platform.system()} {platform.machine()}")
        return False


def registrar(medicoes: list[Medicao], arquivo: str = "energia.json") -> dict:
    total_e = sum(m.energia_kwh for m in medicoes)
    dados = {
        "metodologia": "Green Algorithms (Lannelongue et al., 2021); fator médio do SIN (MCTI)",
        "etapas": [asdict(m) for m in medicoes],
        "total_energia_kwh": total_e,
        "total_energia_wh": total_e * 1000,
        "total_co2_g": sum(m.co2_g for m in medicoes),
        "total_duracao_s": sum(m.duracao_s for m in medicoes),
    }
    pasta = artefatos() / "metrics"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / arquivo).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return dados
