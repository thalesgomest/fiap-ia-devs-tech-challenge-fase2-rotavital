"""Configuração central lida de variáveis de ambiente (.env).

Nenhuma credencial tem valor padrão no código: chaves de API vêm só do ambiente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv é opcional
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    # LLM
    llm_provider: str = _env("LLM_PROVIDER", "ollama")  # ollama | openai | anthropic | offline
    llm_fallback_offline: bool = _env("LLM_FALLBACK_OFFLINE", "1") in ("1", "true", "yes")
    llm_temperature: float = float(_env("LLM_TEMPERATURE", "0.2") or 0.2)
    llm_timeout_s: float = float(_env("LLM_TIMEOUT_S", "120") or 120)
    ollama_base_url: str = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = _env("OLLAMA_MODEL", "llama3.1:8b")
    openai_base_url: str = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_api_key: str = _env("OPENAI_API_KEY")
    openai_model: str = _env("OPENAI_MODEL", "gpt-4o-mini")
    anthropic_model: str = _env("ANTHROPIC_MODEL", "claude-opus-5-5")
    anthropic_effort: str = _env("ANTHROPIC_EFFORT", "medium")

    # Dados
    scenarios_dir: Path = Path(_env("ROTAVITAL_SCENARIOS_DIR") or PROJECT_ROOT / "scenarios")
    database_path: Path = Path(_env("ROTAVITAL_DB") or PROJECT_ROOT / "data" / "rotavital.db")


settings = Settings()
