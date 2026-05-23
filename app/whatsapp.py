import logging
from typing import Optional

from twilio.rest import Client

from app.config import settings


logger = logging.getLogger("rai.whatsapp")

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def send_whatsapp_message(to: str, body: str) -> None:
    """Envía un mensaje WhatsApp vía Twilio.

    `to` debe venir con el prefijo `whatsapp:` (ej. `whatsapp:+34600...`).
    """
    if not settings.twilio_account_sid:
        logger.warning("Twilio no configurado: no se envía '%s' a %s", body[:60], to)
        return

    client = _get_client()
    client.messages.create(
        from_=settings.twilio_whatsapp_from,
        to=to,
        body=body,
    )
