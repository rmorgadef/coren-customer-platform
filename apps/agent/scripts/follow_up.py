"""Seguimiento automatizado de leads inactivos (sección 9 del documento funcional).

Reglas:
- Lead INCOMPLETO sin respuesta durante 24h → 1er recordatorio amable
- Lead INCOMPLETO sin respuesta durante 3 días → 2º recordatorio
- Lead INCOMPLETO sin respuesta tras 2 recordatorios → marcar `frio` + avisar instalador
- Lead CUALIFICADO sin respuesta durante 48h tras la oferta → avisar instalador

Diseñado para ejecutarse periódicamente (cron / systemd timer / n8n cada hora).

Uso:
    python scripts/follow_up.py [--dry-run]
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db
from app.config import settings
from app.handoff import notify_installer
from app.whatsapp import send_whatsapp_message


logger = logging.getLogger("rai.followup")


REMINDER_1 = (
    "Hola 👋 Te escribo de Raidasl. Vi que dejamos la conversación a medias el otro día. "
    "¿Quieres que terminemos de preparar tu presupuesto para el cargador? Solo me faltan un par de datos."
)
REMINDER_2 = (
    "Hola de nuevo, soy RAI de Raidasl. Si todavía te interesa instalar tu cargador, dime y "
    "lo retomamos en menos de 3 minutos. Si ya no lo necesitas, dímelo también y cierro tu ficha. 👍"
)


def _new_status_table() -> None:
    """Tabla auxiliar para no enviar el mismo recordatorio dos veces."""
    with db.get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS follow_ups (
                lead_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (lead_id, kind)
            );
            """
        )


def _already_sent(lead_id: int, kind: str) -> bool:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM follow_ups WHERE lead_id = ? AND kind = ?",
            (lead_id, kind),
        ).fetchone()
        return row is not None


def _mark_sent(lead_id: int, kind: str) -> None:
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO follow_ups (lead_id, kind, sent_at) VALUES (?, ?, ?)",
            (lead_id, kind, datetime.now(timezone.utc).isoformat()),
        )


def _mark_cold(lead_id: int) -> None:
    with db.get_conn() as conn:
        conn.execute("UPDATE leads SET status = 'frio' WHERE id = ?", (lead_id,))


def _hours_since(ts: str) -> float:
    dt = datetime.fromisoformat(ts)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def run(dry_run: bool = False) -> dict:
    db.init_db()
    _new_status_table()

    leads = db.list_leads()
    actions: list[dict] = []

    for lead in leads:
        last_hours = _hours_since(lead["last_contact_at"])

        if lead["status"] == "incompleto":
            if 24 <= last_hours < 72 and not _already_sent(lead["id"], "reminder_1"):
                actions.append({"lead_id": lead["id"], "phone": lead["phone"], "action": "reminder_1"})
                if not dry_run:
                    send_whatsapp_message(to=lead["phone"], body=REMINDER_1)
                    db.append_message(lead["id"], "assistant", REMINDER_1)
                    _mark_sent(lead["id"], "reminder_1")

            elif 72 <= last_hours < 168 and not _already_sent(lead["id"], "reminder_2"):
                actions.append({"lead_id": lead["id"], "phone": lead["phone"], "action": "reminder_2"})
                if not dry_run:
                    send_whatsapp_message(to=lead["phone"], body=REMINDER_2)
                    db.append_message(lead["id"], "assistant", REMINDER_2)
                    _mark_sent(lead["id"], "reminder_2")

            elif last_hours >= 168 and _already_sent(lead["id"], "reminder_2"):
                actions.append({"lead_id": lead["id"], "phone": lead["phone"], "action": "mark_cold"})
                if not dry_run:
                    _mark_cold(lead["id"])
                    answers = db.get_lead_answers(lead["id"])
                    transcript = "\n".join(
                        f"{m['role']}: {m['content']}" for m in db.get_messages(lead["id"])[-10:]
                    )
                    notify_installer(
                        lead_id=lead["id"],
                        phone=lead["phone"],
                        name=lead.get("name"),
                        email=lead.get("email"),
                        reason="lead_frio: sin respuesta tras 2 recordatorios",
                        answers=answers,
                        quote=None,
                        transcript_excerpt=transcript,
                    )

        elif lead["status"] == "cualificado":
            if last_hours >= 48 and not _already_sent(lead["id"], "notify_warm"):
                actions.append({"lead_id": lead["id"], "phone": lead["phone"], "action": "notify_installer_warm"})
                if not dry_run:
                    answers = db.get_lead_answers(lead["id"])
                    quote_json = lead.get("quote_json")
                    quote = json.loads(quote_json) if quote_json else None
                    transcript = "\n".join(
                        f"{m['role']}: {m['content']}" for m in db.get_messages(lead["id"])[-10:]
                    )
                    notify_installer(
                        lead_id=lead["id"],
                        phone=lead["phone"],
                        name=lead.get("name"),
                        email=lead.get("email"),
                        reason="lead_caliente_sin_respuesta_48h",
                        answers=answers,
                        quote=quote,
                        transcript_excerpt=transcript,
                    )
                    _mark_sent(lead["id"], "notify_warm")

    logger.info("Follow-up%s acciones: %s", " (dry-run)" if dry_run else "", actions)
    return {"dry_run": dry_run, "actions": actions}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
