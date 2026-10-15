"""Provedor Claude (Anthropic) via SDK oficial ``anthropic``.

Credenciais: ANTHROPIC_API_KEY ou perfil do ``ant auth login``.

As requisições habilitam o *fallback* do lado do servidor (``fallbacks="default"``):
se o modelo principal recusar uma solicitação, a própria API reencaminha para um
modelo de fallback na mesma chamada.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from rotavital.config import settings
from rotavital.llm.providers.base import ChatResult, LLMError, LLMProvider, ToolCall, ToolSpec, run_tool, with_deadline

FALLBACK_BETA = "server-side-fallback-2026-07-01"
REFUSAL_TEXT = "O modelo recusou esta solicitação. Reformule a pergunta sobre as rotas."


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str = ""):
        self.model = model or settings.anthropic_model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise LLMError('Instale o SDK: pip install "anthropic>=1.0"') from exc
            self._client = anthropic.Anthropic(timeout=settings.llm_timeout_s)
        return self._client

    def _create(self, **kwargs):
        import anthropic

        try:
            return with_deadline(
                lambda: self.client.beta.messages.create(
                    model=self.model,
                    max_tokens=16000,
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                    output_config={"effort": settings.anthropic_effort},
                    **kwargs,
                ),
                settings.llm_timeout_s,
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Credencial Anthropic inválida") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Limite de requisições da Anthropic atingido; tente novamente") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Erro da API Anthropic ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Sem conexão com a API Anthropic") from exc

    @staticmethod
    def _text(response) -> str:
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def complete(self, system: str, prompt: str, max_tokens: int = 3000) -> str:
        response = self._create(system=system, messages=[{"role": "user", "content": prompt}])
        if response.stop_reason == "refusal":
            return REFUSAL_TEXT
        return self._text(response)

    def chat(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: List[ToolSpec],
        max_steps: int = 6,
    ) -> ChatResult:
        tool_map = {t.name: t for t in tools}
        wire_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        history: list = [{"role": m["role"], "content": m["content"]} for m in messages]
        trace: List[ToolCall] = []
        for _ in range(max_steps):
            response = self._create(system=system, messages=history, tools=wire_tools)
            if response.stop_reason == "refusal":
                return ChatResult(REFUSAL_TEXT, trace)
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                return ChatResult(self._text(response), trace)
            # o conteúdo completo (inclusive blocos de raciocínio) volta para o histórico
            history.append({"role": "assistant", "content": response.content})
            results = []
            for block in tool_uses:
                args, result = run_tool(tool_map, block.name, block.input)
                trace.append(ToolCall(block.name, args, result))
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            history.append({"role": "user", "content": results})
        response = self._create(system=system, messages=history, tools=wire_tools, tool_choice={"type": "none"})
        return ChatResult(self._text(response), trace)

    def health(self) -> Tuple[bool, str]:
        try:
            self.client.models.retrieve(self.model)
        except LLMError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001 - qualquer falha = indisponível
            return False, f"Anthropic indisponível: {exc.__class__.__name__}"
        return True, "ok"
