"""Provedor para qualquer API compatível com OpenAI Chat Completions.

Serve para OpenAI, Groq, OpenRouter, LM Studio, vLLM ou o endpoint compatível do
Gemini - basta ajustar OPENAI_BASE_URL, OPENAI_API_KEY e OPENAI_MODEL.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import requests

from rotavital.config import settings
from rotavital.llm.providers.base import ChatResult, LLMError, LLMProvider, ToolCall, ToolSpec, run_tool, with_deadline


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def __init__(self, base_url: str = "", api_key: str = "", model: str = ""):
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model

    def _post(self, payload: dict) -> dict:
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY não definida")
        try:
            resp = with_deadline(
                lambda: requests.post(
                    f"{self.base_url}/chat/completions",
                    json=dict(payload, model=self.model, temperature=settings.llm_temperature),
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=settings.llm_timeout_s,
                ),
                settings.llm_timeout_s,
            )
        except requests.RequestException as exc:
            raise LLMError(f"Falha ao chamar {self.base_url}: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]

    def complete(self, system: str, prompt: str, max_tokens: int = 3000) -> str:
        msg = self._post(
            {
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }
        )
        return (msg.get("content") or "").strip()

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
            msg = self._post({"messages": history, "tools": wire_tools})
            calls = msg.get("tool_calls") or []
            if not calls:
                return ChatResult((msg.get("content") or "").strip(), trace)
            history.append(msg)
            for call in calls:
                fn = call["function"]
                args, result = run_tool(tool_map, fn["name"], fn.get("arguments", "{}"))
                trace.append(ToolCall(fn["name"], args, result))
                history.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        msg = self._post({"messages": history})
        return ChatResult((msg.get("content") or "").strip(), trace)

    def health(self) -> Tuple[bool, str]:
        if not self.api_key:
            return False, "Defina OPENAI_API_KEY no .env"
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
            )
        except requests.RequestException as exc:
            return False, f"Sem conexão com {self.base_url}: {exc}"
        return (resp.status_code < 400, "ok" if resp.status_code < 400 else f"HTTP {resp.status_code}")
