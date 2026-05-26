"""Rama transaccional. Aquí vive el bucle LLM con tools que ejecuta las
acciones reales: cualificación, presupuesto, save_lead, handoff, escalado.

Equivalente conceptual a la rama de Ejecución Transaccional de Coren (la
que habla con MCP/Libra). En RAI las "tools" sustituyen al ERP: cada tool
es una operación atómica sobre el CRM del instalador.
"""

import json
import logging
from dataclasses import dataclass

from app.adapters.llm.base import LLMResponse
from app.circuit_breaker import CircuitBreaker
from app.tools import TOOL_SPECS, dispatch_tool


logger = logging.getLogger("rai.transactional")


@dataclass
class TransactionalResult:
    text: str
    tool_calls_made: list[str]
    last_model: str


class TransactionalBranch:
    name = "transactional"

    def __init__(self, llm: CircuitBreaker, max_tool_iterations: int = 8) -> None:
        self.llm = llm
        self.max_tool_iterations = max_tool_iterations

    def run(
        self,
        *,
        system_prompt: str,
        history: list[dict],
        lead_id: int,
        phone: str,
    ) -> TransactionalResult:
        final_text_parts: list[str] = []
        tool_calls_made: list[str] = []
        last_model: str = ""
        current_messages: list[dict] = list(history)

        for _ in range(self.max_tool_iterations):
            response: LLMResponse = self.llm.complete(
                system=system_prompt,
                messages=current_messages,
                tools=TOOL_SPECS,
                max_tokens=1024,
            )
            last_model = response.model

            if response.text:
                final_text_parts.append(response.text)

            if response.stop_reason != "tool_use" or not response.tool_uses:
                break

            current_messages = current_messages + [
                {"role": "assistant", "content": response.raw_blocks}
            ]

            tool_results = []
            for tu in response.tool_uses:
                tool_calls_made.append(tu["name"])
                try:
                    result = dispatch_tool(tu["name"], tu["input"], lead_id=lead_id, phone=phone)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )
                except Exception as e:
                    logger.exception("Error ejecutando tool %s", tu["name"])
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": f"Error: {e}",
                            "is_error": True,
                        }
                    )

            current_messages = current_messages + [
                {"role": "user", "content": tool_results}
            ]

        return TransactionalResult(
            text="\n".join(p.strip() for p in final_text_parts if p and p.strip()),
            tool_calls_made=tool_calls_made,
            last_model=last_model,
        )
