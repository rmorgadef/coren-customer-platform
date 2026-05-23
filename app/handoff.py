import json
import logging
from typing import Optional

import httpx

from app.config import settings


logger = logging.getLogger("rai.handoff")


def notify_installer(
    *,
    lead_id: int,
    phone: str,
    name: Optional[str],
    email: Optional[str],
    reason: str,
    answers: dict,
    quote: Optional[dict],
    transcript_excerpt: str,
) -> None:
    """Envía resumen estructurado del lead al instalador.

    En la maqueta: log estructurado + opcional POST al webhook configurado.
    En producción: cliente WhatsApp / Telegram interno.
    """
    payload = {
        "lead_id": lead_id,
        "phone": phone,
        "name": name,
        "email": email,
        "reason": reason,
        "answers": answers,
        "quote": quote,
        "transcript_excerpt": transcript_excerpt,
    }

    logger.info("HANDOFF al instalador: %s", json.dumps(payload, ensure_ascii=False, indent=2))

    if settings.installer_notification_webhook:
        try:
            httpx.post(settings.installer_notification_webhook, json=payload, timeout=5)
        except Exception as e:
            logger.warning("Fallo al notificar al instalador vía webhook: %s", e)
