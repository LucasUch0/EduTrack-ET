#!/usr/bin/env python3
"""EduTrack-GNN: prepara o ambiente e abre a aplicação no navegador.

Uso
  Windows       duplo clique em iniciar.bat
  Linux/macOS   ./iniciar.sh
  Qualquer um   python iniciar.py [--porta 8000] [--sem-navegador] [--reinstalar] [--verificar]

Até o ambiente ficar pronto, só a biblioteca padrão do Python é usada. O ambiente virtual
fica fora da pasta do projeto, em ~/.edutrack-gnn (no Windows, C:\\Users\\<você>\\.edutrack-gnn),
para não ser sincronizado pelo OneDrive nem esbarrar no limite de caminho do Windows. Tudo o
que o pip escreve vai para ~/.edutrack-gnn/instalacao.log.

A cada início o script confere se fastapi, uvicorn, numpy e PyYAML importam de fato no
ambiente; se algum faltar, instala, tentando três listas em sequência (versões testadas,
faixas compatíveis, versões mais recentes). O navegador só abre depois que o serviço responde.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
MINIMO = (3, 10)
MODULOS = ("fastapi", "uvicorn", "numpy", "yaml")
PORTAS = tuple(range(8000, 8011))
ETAPAS = (
    ("versões testadas (requirements.txt)", ["-r", str(RAIZ / "requirements.txt")]),
    ("faixas compatíveis com o seu Python (requirements-compat.txt)", ["-r", str(RAIZ / "requirements-compat.txt")]),
    ("versões mais recentes", ["fastapi", "uvicorn", "numpy", "PyYAML"]),
)
VERIFICACAO = (
    "import importlib, json\n"
    "falhas = {}\n"
    "for m in %r:\n"
    "    try:\n"
    "        importlib.import_module(m)\n"
    "    except Exception as e:\n"
    "        falhas[m] = type(e).__name__ + ': ' + str(e)\n"
    "print(json.dumps(falhas))\n"
)
LINHAS_DO_PIP = ("Collecting", "Downloading", "Installing collected", "Successfully installed", "ERROR", "error:",
                 "WARNING: Retrying", "Requirement already satisfied: pip")


class Falha(Exception):
    def __init__(self, motivo: str, dica: str = ""):
        super().__init__(motivo)
        self.motivo, self.dica = motivo, dica


def dizer(texto: str = "") -> None:
    try:
        print(texto, flush=True)
    except UnicodeEncodeError:  # console sem UTF-8: troca os acentos em vez de parar
        print(texto.encode("ascii", "replace").decode("ascii"), flush=True)


def versao_local() -> str:
    m = re.search(r'^versao:\s*"?([\w.\-]+)"?', (RAIZ / "config.yaml").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "?"


def pasta_base() -> Path:
    return Path(os.environ.get("EDUTRACK_AMBIENTE") or Path.home() / ".edutrack-gnn")


def python_do(amb: Path) -> Path:
    return amb / "Scripts" / "python.exe" if os.name == "nt" else amb / "bin" / "python"


def registrar(log: Path, texto: str) -> None:
    try:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {texto}\n")
    except OSError:
        pass


def rodar(cmd: list[str], log: Path) -> int:
    """Executa um comando mostrando só as linhas úteis do pip e guardando tudo no log."""
    registrar(log, "$ " + " ".join(cmd))
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1")
    try:
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              errors="replace", env=env, cwd=RAIZ) as p, open(log, "a", encoding="utf-8") as f:
            for linha in p.stdout:
                f.write(linha)
                if linha.lstrip().startswith(LINHAS_DO_PIP):
                    dizer("   " + linha.strip()[:150])
    except OSError as e:
        registrar(log, f"não executou: {e!r}")
        return 1
    registrar(log, f"código de saída {p.returncode}")
    return p.returncode


def faltando(py: Path) -> dict:
    """Módulos que não importam no ambiente, com o erro de cada um ({} = tudo certo)."""
    try:
        r = subprocess.run([str(py), "-c", VERIFICACAO % (MODULOS,)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        return {"python": str(e)}
    saida = r.stdout.strip().splitlines()
    if r.returncode != 0 or not saida:
        return {"python": (r.stderr.strip() or "o Python do ambiente não respondeu")[-400:]}
    try:
        return json.loads(saida[-1])
    except ValueError:
        return {"python": f"resposta inesperada do Python do ambiente: {saida[-1][:200]}"}


def preparar(reinstalar: bool, log: Path) -> Path:
    base = log.parent
    amb = base / f"venv-py{sys.version_info.major}{sys.version_info.minor}"
    py = python_do(amb)
    registrar(log, f"EduTrack-GNN {versao_local()} · Python {sys.version.split()[0]} ({sys.executable}) · projeto em {RAIZ}")

    if reinstalar and amb.exists():
        dizer("Apagando o ambiente anterior (--reinstalar)...")
        shutil.rmtree(amb, ignore_errors=True)
    falta = faltando(py) if py.exists() else None
    if falta and "python" in falta:
        dizer("O ambiente anterior está danificado; vou recriá-lo.")
        registrar(log, f"ambiente danificado: {falta['python']}")
        shutil.rmtree(amb, ignore_errors=True)
        falta = None
    if not py.exists():
        dizer(f"Criando o ambiente do EduTrack-GNN em {amb} ...")
        try:
            venv.EnvBuilder(with_pip=True, clear=True).create(str(amb))
        except Exception as e:  # noqa: BLE001 - qualquer falha aqui vira a mesma orientação
            registrar(log, f"falha ao criar o ambiente: {e!r}")
            raise Falha("Não consegui criar o ambiente virtual do Python.",
                        "No Windows, reinstale o Python 3.13 de https://www.python.org/downloads/ "
                        "(marque \"Add python.exe to PATH\"). No Linux, instale o pacote python3-venv.") from e

    if falta is None:
        falta = faltando(py)
    if not falta:
        return py
    registrar(log, f"faltando: {falta}")
    dizer("Instalando as dependências (fastapi, uvicorn, numpy, PyYAML).")
    dizer("Na primeira vez leva alguns minutos e precisa de internet.")
    for i, (nome, args) in enumerate(ETAPAS, 1):
        dizer(f"[{i}/{len(ETAPAS)}] {nome}")
        if i == 2:
            rodar([str(py), "-m", "pip", "install", "--upgrade", "pip"], log)
        rodar([str(py), "-m", "pip", "install", *args], log)
        falta = faltando(py)
        if not falta:
            dizer("Dependências prontas.")
            return py
        registrar(log, f"ainda faltando: {falta}")
    detalhe = "; ".join(f"{m}: {e}" for m, e in falta.items())
    raise Falha(f"As dependências não foram instaladas ({detalhe[:300]}).",
                "Confira a conexão com a internet (o pip baixa os pacotes do PyPI) e rode o iniciar de novo. "
                "Se continuar, use o Python 3.13 de https://www.python.org/downloads/ e rode com --reinstalar.")


def em_uso(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", porta))
            return False
        except OSError:
            return True


def ja_rodando(versao: str) -> int | None:
    """Porta de um EduTrack-GNN desta mesma versão já aberto (duplo clique repetido)."""
    for porta in PORTAS:
        if not em_uso(porta):
            continue
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/saude", timeout=2) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - outra aplicação na porta
            continue
        if d.get("status") == "ok" and d.get("versao") == versao and "habilidades" in d:
            return porta
    return None


def escolher_porta(preferida: int) -> int:
    for porta in [preferida] + [p for p in PORTAS if p != preferida]:
        if not em_uso(porta):
            return porta
    raise Falha("As portas 8000 a 8010 estão ocupadas por outros programas.",
                "Feche-os ou escolha outra porta: python iniciar.py --porta 8123")


def quando_pronto(url: str, abrir: bool) -> None:
    limite = time.time() + 180
    while True:
        try:
            with urllib.request.urlopen(url + "api/saude", timeout=3) as r:
                if r.status == 200:
                    break
        except Exception:  # noqa: BLE001 - ainda subindo
            pass
        if time.time() > limite:
            dizer(f"O serviço está demorando a responder. Quando ele subir, abra {url} no navegador.")
            return
        time.sleep(0.4)
    try:  # carrega os dados antes de abrir a página, para a primeira tela vir completa
        urllib.request.urlopen(url + "api/interface", timeout=120).read()
    except Exception:  # noqa: BLE001 - a própria página mostra o erro, se houver
        pass
    linha = "=" * 66
    dizer(linha)
    dizer(f" EduTrack-GNN {versao_local()} rodando em {url}")
    dizer(f" Documentação da API: {url}docs")
    dizer(" Deixe esta janela aberta enquanto usa. Para encerrar, feche-a ou tecle Ctrl+C.")
    dizer(linha)
    if abrir:
        webbrowser.open(url)


def servir(porta: int, abrir: bool) -> int:
    """Roda dentro do ambiente virtual: sobe o serviço e abre o navegador quando ele responde."""
    sys.path.insert(0, str(RAIZ))
    os.chdir(RAIZ)
    try:
        import uvicorn

        from edutrack.api.main import app
    except Exception as e:  # noqa: BLE001
        dizer(f"ERRO ao carregar o serviço: {type(e).__name__}: {e}")
        return 1
    url = f"http://127.0.0.1:{porta}/"
    threading.Thread(target=quando_pronto, args=(url, abrir), daemon=True).start()
    uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning", access_log=False)).run()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prepara o ambiente e abre o EduTrack-GNN no navegador.")
    ap.add_argument("--porta", type=int, default=PORTAS[0], help="porta preferida (padrão: 8000)")
    ap.add_argument("--sem-navegador", action="store_true", help="não abre o navegador")
    ap.add_argument("--reinstalar", action="store_true", help="apaga e recria o ambiente virtual")
    ap.add_argument("--verificar", action="store_true", help="só prepara o ambiente e confere as dependências")
    ap.add_argument("--servir", action="store_true", help=argparse.SUPPRESS)  # uso interno, já no ambiente
    a = ap.parse_args(argv)
    if a.servir:
        return servir(a.porta, not a.sem_navegador)

    versao = versao_local()
    dizer(f"EduTrack-GNN {versao} · Python {sys.version.split()[0]}")
    if sys.version_info < MINIMO:
        dizer(f"ERRO: este é o Python {sys.version.split()[0]}; o EduTrack-GNN precisa do 3.10 ou mais novo.")
        dizer("Instale o Python 3.13 de https://www.python.org/downloads/ e rode de novo.")
        return 1
    base = pasta_base()
    log = base / "instalacao.log"
    try:
        base.mkdir(parents=True, exist_ok=True)
        py = preparar(a.reinstalar, log)
        if a.verificar:
            dizer(f"Ambiente pronto: {py}")
            return 0
        aberta = ja_rodando(versao)
        if aberta:
            url = f"http://127.0.0.1:{aberta}/"
            dizer(f"O EduTrack-GNN já está aberto em {url}" + ("; abrindo o navegador." if not a.sem_navegador else "."))
            if not a.sem_navegador:
                webbrowser.open(url)
            return 0
        porta = escolher_porta(a.porta)
    except Falha as f:
        dizer()
        dizer(f"ERRO: {f.motivo}")
        if f.dica:
            dizer(f.dica)
        dizer(f"Registro completo: {log}")
        return 1

    dizer(f"Iniciando o serviço em http://127.0.0.1:{porta}/ ...")
    cmd = [str(py), str(RAIZ / "iniciar.py"), "--servir", "--porta", str(porta)]
    if a.sem_navegador:
        cmd.append("--sem-navegador")
    proc = subprocess.Popen(cmd, cwd=RAIZ)
    while True:
        try:
            return proc.wait()
        except KeyboardInterrupt:  # o Ctrl+C também chega ao serviço, que encerra sozinho
            continue


if __name__ == "__main__":
    sys.exit(main())
