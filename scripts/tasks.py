"""Tarefas de ambiente chamadas pelo Makefile (multiplataforma: Windows, macOS, Linux).

A lógica que dependeria do shell (criar venv, limpar caches, diagnosticar o ambiente)
fica aqui em Python, para que o Makefile seja idêntico em todos os sistemas.

Este script roda com QUALQUER Python 3 instalado: ele mesmo procura um interpretador
3.11+ para criar o ambiente virtual. Para forçar um interpretador específico, defina a
variável de ambiente ROTAVITAL_PYTHON (ex.: make setup PYTHON="C:/Python312/python.exe").

Uso: python scripts/tasks.py {setup|doctor|clean|reset}
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / "venv"
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
STAMP = VENV / ".instalado"
MIN_VERSION = (3, 11)
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b")


def _ok(msg):
    print(f"  [ok]    {msg}")


def _warn(msg):
    print(f"  [aviso] {msg}")


def _fail(msg):
    print(f"  [erro]  {msg}")


def _version_of(cmd):
    """Retorna (major, minor) do interpretador ou None se não existir."""
    try:
        out = subprocess.run(
            cmd + ["-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        major, minor = out.stdout.split()
        return int(major), int(minor)
    except ValueError:
        return None


def find_python():
    """Procura um Python >= 3.11 (o mais novo primeiro)."""
    forced = os.environ.get("ROTAVITAL_PYTHON")
    if forced:
        version = _version_of([forced])
        return ([forced], version) if version else (None, None)
    candidates = []
    if IS_WINDOWS:
        candidates += [["py", f"-3.{m}"] for m in (13, 12, 11)]
        candidates += [["python"], ["python3"]]
    else:
        candidates += [[f"python3.{m}"] for m in (13, 12, 11)]
        candidates += [["python3"], ["python"]]
    candidates.append([sys.executable])
    for cmd in candidates:
        version = _version_of(cmd)
        if version and version >= MIN_VERSION:
            return cmd, version
    return None, None


def _install_hint():
    if IS_WINDOWS:
        return "winget install Python.Python.3.11"
    if sys.platform == "darwin":
        return "brew install python@3.11"
    return "sudo apt install python3.11 python3.11-venv"


def _remove_venv():
    """Apaga o venv tentando por alguns segundos (no Windows, o editor pode prender o python.exe)."""
    for _ in range(10):
        shutil.rmtree(VENV, ignore_errors=True)
        if not VENV.exists():
            return True
        time.sleep(1)
    _fail(
        "não foi possível apagar a pasta venv: algum programa está usando o Python dela. "
        "Feche terminais e o editor (ex.: VS Code) que usem esse venv e rode o comando de novo."
    )
    return False


def _venv_healthy():
    return (VENV / "pyvenv.cfg").exists() and _version_of([str(VENV_PYTHON)]) is not None


def setup():
    """Cria o venv (se preciso) e instala as dependências."""
    if VENV.exists() and not _venv_healthy():
        print("Ambiente virtual incompleto ou corrompido; recriando...")
        if not _remove_venv():
            return 1
    if not VENV_PYTHON.exists():
        cmd, version = find_python()
        if not cmd:
            _fail(f"Python {MIN_VERSION[0]}.{MIN_VERSION[1]}+ não encontrado. Instale com: {_install_hint()}")
            return 1
        print(f"Criando ambiente virtual com Python {version[0]}.{version[1]} ({' '.join(cmd)})...")
        if subprocess.run(cmd + ["-m", "venv", str(VENV)]).returncode != 0:
            _fail("falha ao criar o venv (no Linux, instale o pacote python3.11-venv)")
            return 1
    print("Instalando dependências...")
    steps = [
        ["-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip"],
        ["-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(ROOT / "requirements.txt")],
        ["-m", "pip", "install", "--disable-pip-version-check", "-q", "-e", str(ROOT)],
    ]
    for args in steps:
        if subprocess.run([str(VENV_PYTHON)] + args).returncode != 0:
            _fail("falha ao instalar dependências (verifique a conexão com a internet)")
            return 1
    env_file, example = ROOT / ".env", ROOT / ".env.example"
    if not env_file.exists() and example.exists():
        shutil.copy(example, env_file)
        print("Arquivo .env criado a partir de .env.example")
    STAMP.write_text("ok", encoding="utf-8")
    print("Ambiente pronto.")
    return 0


def doctor():
    """Diagnostica o ambiente e diz exatamente o que falta."""
    print("Diagnóstico do ambiente RotaVital\n")
    errors = 0

    cmd, version = find_python()
    if cmd:
        _ok(f"Python {version[0]}.{version[1]} disponível ({' '.join(cmd)})")
    else:
        _fail(f"Python 3.11+ não encontrado. Instale com: {_install_hint()}")
        errors += 1

    if VENV_PYTHON.exists() and STAMP.exists():
        venv_version = _version_of([str(VENV_PYTHON)])
        if venv_version and venv_version < MIN_VERSION:
            _fail(f"venv usa Python {venv_version[0]}.{venv_version[1]}; rode 'make reset' e depois 'make setup'")
            errors += 1
        else:
            missing = subprocess.run(
                [str(VENV_PYTHON), "-c", "import fastapi, uvicorn, requests, anthropic, rotavital"],
                capture_output=True,
            ).returncode
            if missing:
                _fail("dependências incompletas no venv; rode 'make setup'")
                errors += 1
            else:
                _ok("ambiente virtual e dependências instalados")
    elif VENV_PYTHON.exists():
        _warn("ambiente virtual existe, mas a instalação não foi concluída (será feita por 'make demo' ou 'make setup')")
    else:
        _warn("ambiente virtual ainda não criado (será criado automaticamente por 'make demo' ou 'make setup')")

    scenarios = list((ROOT / "scenarios").glob("*.json"))
    if scenarios:
        _ok(f"{len(scenarios)} cenário(s) em scenarios/")
    else:
        _fail("nenhum cenário em scenarios/; rode 'make cenarios'")
        errors += 1

    if (ROOT / ".env").exists():
        _ok("arquivo .env presente")
    else:
        _warn("sem .env (será criado no setup; sem ele o padrão é Ollama com fallback offline)")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex(("127.0.0.1", 8000)) == 0:
            _warn("porta 8000 em uso (o app já está rodando ou outro programa ocupa a porta)")
        else:
            _ok("porta 8000 livre")

    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as resp:
            models = {m.get("name", "") for m in json.load(resp).get("models", [])}
        if OLLAMA_MODEL in models or f"{OLLAMA_MODEL}:latest" in models:
            _ok(f"Ollama rodando com o modelo {OLLAMA_MODEL}")
        else:
            _warn(f"Ollama rodando, mas sem o modelo. Rode: make llm   (ollama pull {OLLAMA_MODEL})")
    except Exception:
        _warn("Ollama não encontrado: o assistente funcionará em MODO OFFLINE (opcional: https://ollama.com)")

    print()
    if errors:
        print(f"{errors} problema(s) impedem a execução. Corrija os itens [erro] acima.")
        return 1
    print("Tudo certo. Rode 'make demo' (ou 'make app').")
    return 0


def clean():
    names = {"__pycache__", ".pytest_cache", ".ruff_cache"}
    removed = 0
    for path in ROOT.rglob("*"):
        if path.is_dir() and path.name in names and VENV not in path.parents:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    print(f"{removed} pasta(s) de cache removida(s).")
    return 0


def reset():
    clean()
    if VENV.exists():
        if not _remove_venv():
            return 1
        print("Ambiente virtual removido. Rode 'make setup' para recriar.")
    return 0


TASKS = {"setup": setup, "doctor": doctor, "clean": clean, "reset": reset}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        print(__doc__)
        sys.exit(2)
    sys.exit(TASKS[sys.argv[1]]())
