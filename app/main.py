"""FastAPI app: webhook Twilio WhatsApp + endpoint de inspección de leads."""

import logging

from fastapi import FastAPI, Form, Response
from fastapi.responses import JSONResponse

from app import db
from app.agent import handle_user_message


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("rai.main")

app = FastAPI(title="RAI — Raidasl WhatsApp Assistant (demo)")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/")
def healthcheck() -> dict:
    return {"status": "ok", "service": "rai-whatsapp-demo"}


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    ProfileName: str = Form(default=""),
) -> Response:
    """Endpoint que recibe los mensajes del Twilio WhatsApp Sandbox.

    Twilio envía form-encoded: From=whatsapp:+34..., Body=texto, ProfileName=...
    Respondemos vacío (200) y enviamos la respuesta vía la API outbound de Twilio
    para evitar el límite de 160 chars / tags del TwiML inline en respuestas
    largas con múltiples turnos.
    """
    logger.info("WhatsApp inbound de %s (%s): %s", From, ProfileName, Body)

    try:
        reply = handle_user_message(phone=From, user_text=Body)
    except Exception:
        logger.exception("Error procesando mensaje entrante")
        reply = "Ahora mismo no puedo atenderte bien. Un compañero te contactará en cuanto pueda."

    # Importar aquí para no fallar el arranque si Twilio no está configurado
    from app.whatsapp import send_whatsapp_message

    try:
        send_whatsapp_message(to=From, body=reply)
    except Exception:
        logger.exception("Error enviando respuesta WhatsApp")

    # Respuesta TwiML vacía (ack)
    return Response(content="<Response/>", media_type="application/xml")


@app.get("/leads")
def list_leads() -> JSONResponse:
    """Endpoint de inspección rápida para la demo."""
    return JSONResponse(db.list_leads())


@app.get("/leads/{lead_id}/messages")
def get_lead_messages(lead_id: int) -> JSONResponse:
    return JSONResponse(db.get_messages(lead_id))
