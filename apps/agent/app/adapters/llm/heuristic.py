"""Fallback determinista sin LLM. Última línea de defensa cuando el primary
y el fallback fallan o agotan timeouts. Equivalente conceptual al "mensaje
degradado" cuando Coren no llega al circuito completo.

Importante: NO intenta replicar al agente. Solo garantiza que el cliente
recibe una respuesta humana y la conversación queda escalada para revisión.
"""

from app.adapters.llm.base import LLMClient, LLMResponse


DEGRADED_MESSAGE = (
    "Disculpa, ahora mismo estoy teniendo problemas para atenderte como debería. "
    "Le he pasado tu mensaje a un compañero de Raidasl y te contactará en cuanto pueda. "
    "Gracias por la paciencia 🙏"
)


class HeuristicFallback(LLMClient):
    name = "heuristic:degraded"

    def complete(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        # Adjuntamos una tool_use simulada para que el coordinator escale.
        # Solo lo hacemos si la lista de tools incluye `escalate_to_human`.
        tool_uses: list[dict] = []
        if tools and any(t.get("name") == "escalate_to_human" for t in tools):
            tool_uses.append(
                {
                    "id": "heuristic_escalation",
                    "name": "escalate_to_human",
                    "input": {
                        "reason": "atascada",
                        "note": "fallback degradado: primary y fallback LLM caídos",
                    },
                }
            )

        return LLMResponse(
            text=DEGRADED_MESSAGE,
            tool_uses=tool_uses,
            stop_reason="end_turn",
            raw_blocks=[],
            model="heuristic",
            confidence=0.0,
        )
