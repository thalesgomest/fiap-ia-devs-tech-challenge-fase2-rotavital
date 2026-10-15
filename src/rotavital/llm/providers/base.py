"""Interface comum dos provedores de LLM.

Cada provedor implementa duas operações:
  * ``complete``: uma chamada única (relatórios e instruções);
  * ``chat``: conversa com *function calling* - o modelo decide quais ferramentas
    consultar (rotas, paradas, simulações) e responde com base nos resultados reais.
O laço de ferramentas fica dentro de cada adaptador porque o formato das mensagens de
ferramenta difere entre APIs (Ollama, OpenAI e Anthropic).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

MAX_TOOL_RESULT_CHARS = 6000
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm")


class LLMError(RuntimeError):
    """Falha de comunicação ou resposta inválida do provedor."""


class ToolsUnsupported(LLMError):
    """O modelo configurado não suporta chamada de ferramentas."""


def with_deadline(fn: Callable[[], Any], seconds: float) -> Any:
    """Executa ``fn`` com prazo TOTAL de ``seconds``.

    O ``timeout`` das bibliotecas HTTP mede o tempo sem receber dados, não a duração
    total. Um modelo local carregando na CPU pode segurar a conexão por muitos minutos;
    aqui a chamada é abandonada no prazo e o app segue com o texto de contingência.
    """
    future = _executor.submit(fn)
    try:
        return future.result(timeout=seconds)
    except FutureTimeout:
        raise LLMError(
            f"a LLM não respondeu em {seconds:.0f} s (modelo pesado para este hardware? "
            "tente um modelo menor ou aumente LLM_TIMEOUT_S)"
        ) from None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    result: str


@dataclass
class ChatResult:
    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)


def run_tool(tools: Dict[str, ToolSpec], name: str, arguments: Any) -> Tuple[Dict[str, Any], str]:
    """Executa uma ferramenta com argumentos vindos do modelo, sem nunca lançar exceção."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            return {}, json.dumps({"erro": "argumentos não são JSON válido"})
    arguments = arguments if isinstance(arguments, dict) else {}
    spec = tools.get(name)
    if spec is None:
        return arguments, json.dumps({"erro": f"ferramenta '{name}' não existe"})
    try:
        result = spec.handler(**arguments)
    except TypeError as exc:
        result = {"erro": f"argumentos inválidos: {exc}"}
    except Exception as exc:  # noqa: BLE001 - o erro volta para o modelo corrigir
        result = {"erro": str(exc)}
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + "... [truncado]"
    return arguments, text


class LLMProvider(ABC):
    name: str = ""
    model: str = ""
    offline: bool = False

    @abstractmethod
    def complete(self, system: str, prompt: str, max_tokens: int = 3000) -> str:
        ...

    @abstractmethod
    def chat(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: List[ToolSpec],
        max_steps: int = 6,
    ) -> ChatResult:
        """``messages`` usa papéis 'user'/'assistant' e conteúdo em texto."""

    @abstractmethod
    def health(self) -> Tuple[bool, str]:
        ...
