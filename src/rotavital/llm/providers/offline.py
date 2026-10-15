"""Modo offline: sem LLM. Relatórios e chat usam modelos de texto determinísticos.

Garante que a aplicação funcione (e que os testes rodem) mesmo sem Ollama ou chave de
API. A interface sinaliza claramente quando este modo está ativo.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from rotavital.llm.providers.base import ChatResult, LLMProvider, ToolSpec


class OfflineProvider(LLMProvider):
    name = "offline"
    model = "modelos determinísticos"
    offline = True

    def __init__(self, reason: str = "LLM_PROVIDER=offline"):
        self.reason = reason

    def complete(self, system: str, prompt: str, max_tokens: int = 3000) -> str:
        raise NotImplementedError("Use os templates de rotavital.llm.templates")

    def chat(self, system: str, messages: List[Dict[str, str]], tools: List[ToolSpec], max_steps: int = 6) -> ChatResult:
        raise NotImplementedError("Use rotavital.llm.assistant.offline_answer")

    def health(self) -> Tuple[bool, str]:
        return True, self.reason
