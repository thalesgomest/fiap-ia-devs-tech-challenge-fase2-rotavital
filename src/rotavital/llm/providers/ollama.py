"""Provedor padrão: LLM local via Ollama (Llama 3.1, Qwen 2.5, Mistral...).

Gratuito, offline e sem chave de API - o avaliador só precisa de ``ollama pull``.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import requests

from rotavital.config import settings
from rotavital.llm.providers.base import (
    ChatResult,
    LLMError,
    LLMProvider,
    ToolCall,
    ToolSpec,
    ToolsUnsupported,
    run_tool,
    with_deadline,
)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str = "", model: str = ""):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model

    def _post(self, payload: dict) -> dict:
        try:
            resp = with_deadline(
                lambda: requests.post(f"{self.base_url}/api/chat", json=payload, timeout=settings.llm_timeout_s),
                settings.llm_timeout_s,
            )
        except requests.RequestException as exc:
            raise LLMError(f"Ollama indisponível em {self.base_url}: {exc}") from exc
        if resp.status_code == 400 and "does not support tools" in resp.text:
            raise ToolsUnsupported(f"O modelo {self.model} não suporta ferramentas")
        if resp.status_code >= 400:
            raise LLMError(f"Ollama HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def _options(self) -> dict:
        return {"temperature": settings.llm_temperature, "num_ctx": 8192}

    def complete(self, system: str, prompt: str, max_tokens: int = 3000) -> str:
        data = self._post(
            {
                "model": self.model,
                "stream": False,
                "options": dict(self._options(), num_predict=max_tokens),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }
        )
        return data.get("message", {}).get("content", "").strip()

    def chat(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: List[ToolSpec],
        max_steps: int = 6,
    ) -> ChatResult:
        tool_map = {t.name: t for t in tools}
        wire_tools = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
            }
            for t in tools
        ]
        history = [{"role": "system", "content": system}] + list(messages)
        trace: List[ToolCall] = []
        for _ in range(max_steps):
            data = self._post(
                {
                    "model": self.model,
                    "stream": False,
                    "options": self._options(),
                    "messages": history,
                    "tools": wire_tools,
                }
            )
            msg = data.get("message", {})
            calls = msg.get("tool_calls") or []
            if not calls:
                return ChatResult(msg.get("content", "").strip(), trace)
            history.append(msg)
            for call in calls:
                fn = call.get("function", {})
                args, result = run_tool(tool_map, fn.get("name", ""), fn.get("arguments", {}))
                trace.append(ToolCall(fn.get("name", ""), args, result))
                history.append({"role": "tool", "content": result, "tool_name": fn.get("name", "")})
        # limite de passos atingido: pede a resposta final sem ferramentas
        data = self._post(
            {"model": self.model, "stream": False, "options": self._options(), "messages": history}
        )
        return ChatResult(data.get("message", {}).get("content", "").strip(), trace)

    def health(self) -> Tuple[bool, str]:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            resp.raise_for_status()
        except requests.RequestException:
            return False, f"Ollama não encontrado em {self.base_url}. Instale e rode `ollama serve`."
        names = {m.get("name", "") for m in resp.json().get("models", [])}
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in names and self.model not in names:
            return False, f"Modelo não baixado. Execute: ollama pull {self.model}"
        return True, "ok"
