"""Punto de entrada del agente.

Mantiene la firma `handle_user_message(phone, user_text, profile_name)` para
no romper main.py ni los scripts. Internamente delega en el Coordinator
(3 ramas en paralelo + circuit breaker primary→fallback→heurística).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app import db
from app.adapters.llm.factory import build_circuit_breaker
from app.branches.conversational import ConversationalBranch
from app.branches.security import SecurityBranch
from app.branches.transactional import TransactionalBranch
from app.coordinator import Coordinator


logger = logging.getLogger("rai.agent")

RETURNING_CUSTOMER_GAP_MINUTES = 60

_coordinator: Optional[Coordinator] = None


def _get_coordinator() -> Coordinator:
    global _coordinator
    if _coordinator is None:
        breaker = build_circuit_breaker()
        _coordinator = Coordinator(
            security=SecurityBranch(),
            conversational=ConversationalBranch(),
            transactional=TransactionalBranch(llm=breaker),
        )
    return _coordinator


def _build_history(lead_id: int) -> list[dict]:
    msgs = db.get_messages(lead_id)
    return [{"role": m["role"], "content": m["content"]} for m in msgs]


def _detect_returning_customer(lead: dict) -> Optional[str]:
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

    coordinator = _get_coordinator()
    outcome = coordinator.handle(
        lead_id=lead_id,
        phone=phone,
        user_text=user_text,
        history=history,
        returning_context=returning_context,
    )

    logger.info(
        "turn done lead=%d security=%s model=%s tools=%s",
        lead_id,
        outcome.security.action,
        outcome.model_used,
        outcome.transactional.tool_calls_made if outcome.transactional else [],
    )

    db.append_message(lead_id, "assistant", outcome.reply_text)
    return outcome.reply_text
