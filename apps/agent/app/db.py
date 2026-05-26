import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    name TEXT,
    email TEXT,
    status TEXT NOT NULL DEFAULT 'incompleto',
    answers_json TEXT NOT NULL DEFAULT '{}',
    quote_json TEXT,
    escalation_reason TEXT,
    first_contact_at TEXT NOT NULL,
    last_contact_at TEXT NOT NULL,
    origin TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_lead ON messages(lead_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def get_or_create_lead(phone: str, origin: str = "whatsapp") -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM leads WHERE phone = ?", (phone,)).fetchone()
        if row:
            return dict(row)
        now = _now()
        cur = conn.execute(
            "INSERT INTO leads (phone, status, first_contact_at, last_contact_at, origin) "
            "VALUES (?, 'incompleto', ?, ?, ?)",
            (phone, now, now, origin),
        )
        return {
            "id": cur.lastrowid,
            "phone": phone,
            "name": None,
            "email": None,
            "status": "incompleto",
            "answers_json": "{}",
            "quote_json": None,
            "escalation_reason": None,
            "first_contact_at": now,
            "last_contact_at": now,
            "origin": origin,
        }


def get_messages(lead_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE lead_id = ? ORDER BY id ASC",
            (lead_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def append_message(lead_id: int, role: str, content: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (lead_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (lead_id, role, content, _now()),
        )
        conn.execute(
            "UPDATE leads SET last_contact_at = ? WHERE id = ?",
            (_now(), lead_id),
        )


def update_lead_answers(lead_id: int, answers: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE leads SET answers_json = ? WHERE id = ?",
            (json.dumps(answers, ensure_ascii=False), lead_id),
        )


def get_lead_answers(lead_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT answers_json FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        return json.loads(row["answers_json"]) if row else {}


def set_lead_quote(lead_id: int, quote: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE leads SET quote_json = ?, status = 'cualificado' WHERE id = ?",
            (json.dumps(quote, ensure_ascii=False), lead_id),
        )


def set_lead_contact(lead_id: int, name: Optional[str], email: Optional[str]) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE leads SET name = COALESCE(?, name), email = COALESCE(?, email) WHERE id = ?",
            (name, email, lead_id),
        )


def escalate_lead(lead_id: int, reason: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE leads SET status = 'escalado', escalation_reason = ? WHERE id = ?",
            (reason, lead_id),
        )


def list_leads() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM leads ORDER BY last_contact_at DESC").fetchall()
        return [dict(r) for r in rows]
