"""FastAPI app: webhook Twilio WhatsApp + dashboard + endpoints de inspección/KPIs."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.request_validator import RequestValidator

from app import db
from app.agent import handle_user_message
from app.auth import require_admin_key
from app.config import settings
from app.kpis import compute_kpis


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("rai.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="RAI — Raidasl WhatsApp Assistant (demo)", lifespan=lifespan)

# El dashboard vive en apps/web-portal/. Desde apps/agent/app/main.py son 3
# niveles arriba: app/ → agent/ → apps/ → repo/, luego bajamos a web-portal/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DASHBOARD_HTML = (_REPO_ROOT / "apps" / "web-portal" / "dashboard.html").read_text(encoding="utf-8")


@app.get("/")
def healthcheck() -> dict:
    return {"status": "ok", "service": "rai-whatsapp-demo"}


async def _verify_twilio_signature(request: Request, form_data: dict) -> None:
    if not settings.twilio_auth_token:
        logger.warning("TWILIO_AUTH_TOKEN no configurado, se omite validación de firma")
        return

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        raise HTTPException(status_code=403, detail="Falta cabecera X-Twilio-Signature")

    validator = RequestValidator(settings.twilio_auth_token)
    url = str(request.url)
    if not validator.validate(url, form_data, signature):
        logger.warning("Firma Twilio inválida para %s", url)
        raise HTTPException(status_code=403, detail="Firma Twilio inválida")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    ProfileName: str = Form(default=""),
) -> Response:
    form = await request.form()
    await _verify_twilio_signature(request, dict(form))

    logger.info("WhatsApp inbound de %s (%s): %s", From, ProfileName, Body)

    try:
        reply = handle_user_message(phone=From, user_text=Body, profile_name=ProfileName)
    except Exception:
        logger.exception("Error procesando mensaje entrante")
        reply = "Ahora mismo no puedo atenderte bien. Un compañero te contactará en cuanto pueda."

    from app.whatsapp import send_whatsapp_message

    try:
        send_whatsapp_message(to=From, body=reply)
    except Exception:
        logger.exception("Error enviando respuesta WhatsApp")

    return Response(content="<Response/>", media_type="application/xml")


@app.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_admin_key)])
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/leads", dependencies=[Depends(require_admin_key)])
def list_leads() -> JSONResponse:
    return JSONResponse(db.list_leads())


@app.get("/leads/{lead_id}/messages", dependencies=[Depends(require_admin_key)])
def get_lead_messages(lead_id: int) -> JSONResponse:
    return JSONResponse(db.get_messages(lead_id))


@app.get("/kpis", dependencies=[Depends(require_admin_key)])
def kpis() -> JSONResponse:
    return JSONResponse(compute_kpis())
