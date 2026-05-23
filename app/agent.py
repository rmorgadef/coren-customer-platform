"""Bucle de conversación con Claude usando tool use.

Mantiene el historial en SQLite (no en memoria de proceso) para que sobreviva
a reinicios del servidor y múltiples conversaciones simultáneas.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from anthropic import Anthropic

from app import db
from app.config import settings
from app.prompts import SYSTEM_PROMPT
from app.tools import TOOL_SPECS, dispatch_tool


logger = logging.getLogger("rai.agent")

_client: Optional[Anthropic] = None

# Si han pasado más de N minutos desde el último mensaje, consideramos que es
# una conversación "nueva" del mismo cliente y RAI da contexto de retorno.
RETURNING_CUSTOMER_GAP_MINUTES = 60


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _build_history(lead_id: int) -> list[dict]:
    """Reconstruye `messages` para la API a partir de la transcripción persistida."""
    msgs = db.get_messages(lead_id)
    return [{"role": m["role"], "content": m["content"]} for m in msgs]


def _format_system_prompt(returning_context: Optional[str]) -> str:
    prompt = SYSTEM_PROMPT.replace("{privacy_policy_url}", settings.privacy_policy_url)
    if returning_context:
        prompt += f"\n\n# Contexto de cliente recurrente\n{returning_context}\n"
    return prompt


def _detect_returning_customer(lead: dict) -> Optional[str]:
    """Si el lead ya existía y han pasado >N minutos desde el último contacto,
    devuelve un bloque de contexto para que RAI salude reconociendo el retorno.
    """
    if not lead.get("last_contact_at"):
        return None

    msgs = db.get_messages(lead["id"])
    if len(msgs) <= 1:
        return None

    try:
        last_ts = datetime.fromisoformat(lead["last_contact_at"])
    except ValueError:
        return None

    gap_minutes = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
    if gap_minutes < RETURNING_CUSTOMER_GAP_MINUTES:
        return None

    answers = db.get_lead_answers(lead["id"])
    name = lead.get("name") or answers.get("contact_name")

    parts = ["Este cliente ya ha contactado antes. NO repitas la presentación inicial completa."]
    if name:
        parts.append(f"- Nombre conocido: {name}")
    if answers.get("property_type"):
        parts.append(f"- Tipo de inmueble previo: {answers['property_type']}")
    if answers.get("postal_code"):
        parts.append(f"- CP previo: {answers['postal_code']}")
    if answers.get("vehicle_model"):
        parts.append(f"- Vehículo previo: {answers['vehicle_model']}")
    if lead.get("status") == "cualificado":
        parts.append("- Ya estaba CUALIFICADO. Pregunta si retoma su consulta previa o quiere otra cosa.")
    elif lead.get("status") == "incompleto":
        parts.append("- Su cualificación quedó INCOMPLETA. Ofrece retomar donde lo dejó.")

    return "\n".join(parts)


def handle_user_message(phone: str, user_text: str, profile_name: str = "") -> str:
    """Procesa un mensaje entrante y devuelve la respuesta de texto."""
    db.init_db()
    lead = db.get_or_create_lead(phone)
    lead_id = lead["id"]

    returning_context = _detect_returning_customer(lead)

    db.append_message(lead_id, "user", user_text)

    history = _build_history(lead_id)

    client = _get_client()
    system_prompt = _format_system_prompt(returning_context)

    max_tool_iterations = 8
    final_text_parts: list[str] = []

    current_messages = history

    for _ in range(max_tool_iterations):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=system_prompt,
            tools=TOOL_SPECS,
            messages=current_messages,
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if text_blocks:
            final_text_parts.extend(text_blocks)

        if response.stop_reason != "tool_use" or not tool_uses:
            break

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
                        "content": json.dumps(result, ensure_ascii=False, default=str),
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
