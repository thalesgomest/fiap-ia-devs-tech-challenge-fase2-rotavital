"""Ollama local: Qwen3 com parâmetros reproduzíveis e ferramentas da operação.

Adapta a configuração de inferência validada no projeto RotaMed ao contrato do
RotaVital. A LLM consulta ferramentas; não otimiza nem modifica as rotas.
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
        self.model_digest = None
        self.session = requests.Session()
        # O serviço local não deve ser encaminhado por proxies do ambiente.
        self.session.trust_env = False

    def _post(self, payload: dict) -> dict:
        payload = {"think": settings.ollama_think, "keep_alive": settings.ollama_keep_alive, **payload}
        try:
            resp = with_deadline(
                lambda: self.session.post(
                    f"{self.base_url}/api/chat", json=payload, timeout=settings.llm_timeout_s
                ),
                settings.llm_timeout_s,
            )
        except requests.RequestException as exc:
            raise LLMError(f"Ollama indisponível em {self.base_url}: {exc}") from exc
        if resp.status_code == 400 and "does not support tools" in resp.text:
            raise ToolsUnsupported(f"O modelo {self.model} não suporta ferramentas")
        if resp.status_code >= 400:
            raise LLMError(f"Ollama HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError("Ollama retornou uma resposta que não é JSON válido") from exc
        if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
            raise LLMError("Ollama retornou uma resposta sem mensagem válida")
        return data

    def _options(self) -> dict:
        return {"temperature": settings.llm_temperature, "num_ctx": settings.ollama_context,
                "seed": settings.ollama_seed, "num_predict": settings.ollama_num_predict}

    def complete(self, system: str, prompt: str, max_tokens: int = 3000) -> str:
        data = self._post({
            "model": self.model, "stream": False,
            "options": dict(self._options(), num_predict=max_tokens),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        })
        content = data["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError("Ollama não produziu texto; verifique o modelo e OLLAMA_THINK")
        return content.strip()

    def chat(self, system: str, messages: List[Dict[str, str]], tools: List[ToolSpec],
             max_steps: int = 6) -> ChatResult:
        tool_map = {tool.name: tool for tool in tools}
        wire_tools = [{"type": "function", "function": {
            "name": tool.name, "description": tool.description, "parameters": tool.parameters,
        }} for tool in tools]
        history = [{"role": "system", "content": system}] + list(messages)
        trace: List[ToolCall] = []
        for _ in range(max_steps):
            data = self._post({"model": self.model, "stream": False, "options": self._options(),
                               "messages": history, "tools": wire_tools})
            message = data["message"]
            calls = message.get("tool_calls") or []
            if not isinstance(calls, list):
                raise LLMError("Ollama retornou chamadas de ferramenta inválidas")
            if not calls:
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise LLMError("Ollama retornou resposta vazia ao chat")
                return ChatResult(content.strip(), trace)
            history.append(message)
            for call in calls:
                function = call.get("function", {}) if isinstance(call, dict) else {}
                if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                    raise LLMError("Ollama retornou uma ferramenta sem nome válido")
                name = function["name"]
                args, result = run_tool(tool_map, name, function.get("arguments", {}))
                trace.append(ToolCall(name, args, result))
                history.append({"role": "tool", "tool_name": name, "content": result})
        data = self._post({"model": self.model, "stream": False,
                           "options": self._options(), "messages": history})
        content = data["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError("Limite de consultas atingido sem uma resposta final")
        return ChatResult(content.strip(), trace)

    def health(self) -> Tuple[bool, str]:
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            data = response.json()
            models = data.get("models") if isinstance(data, dict) else None
            if not isinstance(models, list):
                return False, "Ollama retornou uma lista de modelos inválida."
        except (requests.RequestException, ValueError):
            return False, (f"Ollama não encontrado em {self.base_url}. "
                           "No Windows, execute scripts/setup-ollama.ps1; ou inicie ollama serve.")
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        match = next((item for item in models if isinstance(item, dict)
                      and item.get("name") in {wanted, self.model}), None)
        if match is None:
            return False, f"Modelo não disponível: {self.model}. Execute scripts/setup-ollama.ps1 ou ollama pull {self.model}."
        self.model_digest = match.get("digest")
        return True, "ok"
