"""Prompts versionados em arquivos .md (placeholders no formato ``$nome``).

Manter os prompts fora do código facilita iterar, comparar versões no git e citá-los
no relatório técnico.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render(name: str, **values) -> str:
    return Template(load(name)).safe_substitute(**values)
