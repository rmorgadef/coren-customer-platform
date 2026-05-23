"""Bucle de conversación con Claude usando tool use.

Mantiene el historial en SQLite (no en memoria de proceso) para que sobreviva
a reinicios del servidor y múltiples conversaciones simultáneas.
"""

import logging
from typing import Optional

from anthropic import Anthropic

from app import db
from app.config import settings
from app.prompts import SYSTEM_PROMPT
from app.tools import TOOL_SPECS, dispatch_tool


logger = logging.getLogger("rai.agent")

_client: Optional[Anthropic] = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _build_history(lead_id: int) -> list[dict]:
    """Reconstruye `messages` para la API a partir de la transcripción persistida.

    Estrategia simple para la maqueta: almacenamos role=user y role=assistant en
    texto plano. Los resultados de tools se vuelven a calcular si fueran necesarios,
    pero como Claude solo necesita el texto final asistente/usuario para mantener
    la conversación, esta vista es suficiente.
    """
    msgs = db.get_messages(lead_id)
    return [{"role": m["role"], "content": m["content"]} for m in msgs]


def _format_system_prompt() -> str:
    return SYSTEM_PROMPT.replace("{privacy_policy_url}", settings.privacy_policy_url)


def handle_user_message(phone: str, user_text: str) -> str:
    """Procesa un mensaje entrante y devuelve la respuesta de texto para enviar al usuario."""
    db.init_db()
    lead = db.get_or_create_lead(phone)
    lead_id = lead["id"]

    db.append_message(lead_id, "user", user_text)

    history = _build_history(lead_id)

    client = _get_client()
    system_prompt = _format_system_prompt()

    max_tool_iterations = 8
    final_text_parts: list[str] = []

    # API call loop: keep going while the model asks to use tools.
    current_messages = history

    for _ in range(max_tool_iterations):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=system_prompt,
            tools=TOOL_SPECS,
            messages=current_messages,
        )

        # Collect any text the model emitted in this turn
        text_blocks = [b.text for b in response.content if b.type == "text"]
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if text_blocks:
            final_text_parts.extend(text_blocks)

        if response.stop_reason != "tool_use" or not tool_uses:
            break

        # Echo the assistant turn (containing tool_use blocks) into messages,
        # then provide tool_result blocks for each tool_use.
        assistant_blocks = [b.model_dump() for b in response.content]
        current_messages = current_messages + [{"role": "assistant", "content": assistant_blocks}]

        tool_results = []
        for tu in tool_uses:
            try:
                result = dispatch_tool(tu.name, tu.input, lead_id=lead_id, phone=phone)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": _json_dumps(result),
                    }
                )
            except Exception as e:
                logger.exception("Error ejecutando tool %s", tu.name)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"Error: {e}",
                        "is_error": True,
                    }
                )

        current_messages = current_messages + [{"role": "user", "content": tool_results}]

    reply = "\n".join(p.strip() for p in final_text_parts if p and p.strip())
    if not reply:
        reply = "Disculpa, no te he entendido bien. ¿Me lo puedes repetir?"

    db.append_message(lead_id, "assistant", reply)
    return reply


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
