"""Camada de LLM: escolha do provedor, assistente com ferramentas, relatórios e avaliação.

Seleção por variável de ambiente ``LLM_PROVIDER``:
  * ``ollama`` (padrão) - modelo local, gratuito, sem chave;
  * ``openai`` - qualquer API compatível com OpenAI;
  * ``anthropic`` - Claude via SDK oficial;
  * ``offline`` - sem LLM (textos determinísticos).
Se o provedor configurado estiver indisponível e ``LLM_FALLBACK_OFFLINE=1``, a aplicação
cai automaticamente para o modo offline em vez de quebrar.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from rotavital.config import settings
from rotavital.llm.providers.base import LLMProvider
from rotavital.llm.providers.offline import OfflineProvider

_HEALTH_TTL_S = 30.0
_cache: dict = {"at": 0.0, "provider": None, "status": None}


def build_provider(name: Optional[str] = None) -> LLMProvider:
    name = (name or settings.llm_provider).lower()
    if name == "ollama":
        from rotavital.llm.providers.ollama import OllamaProvider

        return OllamaProvider()
    if name == "openai":
        from rotavital.llm.providers.openai_compat import OpenAICompatibleProvider

        return OpenAICompatibleProvider()
    if name == "anthropic":
        from rotavital.llm.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    return OfflineProvider()


def _resolve() -> Tuple[LLMProvider, dict]:
    now = time.monotonic()
    if _cache["provider"] is not None and now - _cache["at"] < _HEALTH_TTL_S:
        return _cache["provider"], _cache["status"]
    configured = build_provider()
    ok, detail = configured.health()
    if ok or not settings.llm_fallback_offline:
        provider = configured
    else:
        provider = OfflineProvider(reason=detail)
    status = {
        "provedor": configured.name,
        "modelo": configured.model,
        "model_digest": getattr(configured, "model_digest", None),
        "disponivel": ok and not configured.offline,
        "modo": "offline" if provider.offline else "llm",
        "detalhe": detail,
    }
    _cache.update(at=now, provider=provider, status=status)
    return provider, status


def get_provider() -> LLMProvider:
    return _resolve()[0]


def llm_status() -> dict:
    return dict(_resolve()[1])


def reset_cache() -> None:
    _cache.update(at=0.0, provider=None, status=None)
