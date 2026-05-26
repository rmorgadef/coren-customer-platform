"""Interfaz común para clientes LLM.

Equivalente al patrón de Coren: Gemma4 (primary on-prem) → Gemini (fallback API).
En RAI: Claude Sonnet 4.6 (primary) → Claude Haiku 4.5 (fallback rápido y barato)
→ HeuristicFallback (degradación total, sin LLM).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    text: str
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"
    raw_blocks: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    # 0.0–1.0 (estimación; opcional). El circuit breaker lo usa para
    # decidir si la respuesta del primary es suficientemente fiable.
    confidence: float = 1.0


class LLMClient(ABC):
    """Contrato mínimo de cualquier LLM (primary, fallback o stub)."""

    name: str = "abstract"

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        ...
