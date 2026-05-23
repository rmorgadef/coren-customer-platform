"""Tests del helper de cliente recurrente (no requiere llamar a Claude)."""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.agent import _detect_returning_customer


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(db.settings, "database_path", path)
    db.init_db()
    yield path
    os.unlink(path)


def _backdate(path: str, lead_id: int, hours: int) -> None:
    past = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE leads SET last_contact_at = ? WHERE id = ?", (past, lead_id))
    conn.commit()
    conn.close()


def test_no_return_for_new_lead():
    lead = db.get_or_create_lead("whatsapp:+34600000001")
    assert _detect_returning_customer(lead) is None


def test_no_return_if_no_previous_messages(temp_db):
    lead = db.get_or_create_lead("whatsapp:+34600000001")
    _backdate(temp_db, lead["id"], 5)
    refreshed = db.list_leads()[0]
    # No messages yet ⇒ no es cliente recurrente
    assert _detect_returning_customer(refreshed) is None


def test_detects_returning_after_gap(temp_db):
    lead = db.get_or_create_lead("whatsapp:+34600000001")
    db.append_message(lead["id"], "user", "hola")
    db.append_message(lead["id"], "assistant", "¡Hola! Soy RAI...")
    db.update_lead_answers(lead["id"], {"property_type": "unifamiliar", "postal_code": "28001"})
    db.set_lead_contact(lead["id"], "Ana", "ana@x.com")
    _backdate(temp_db, lead["id"], 3)  # 3h gap > 60min

    refreshed = db.list_leads()[0]
    ctx = _detect_returning_customer(refreshed)
    assert ctx is not None
    assert "Ana" in ctx
    assert "28001" in ctx
    assert "unifamiliar" in ctx
    assert "INCOMPLETA" in ctx


def test_no_return_within_gap_threshold(temp_db):
    lead = db.get_or_create_lead("whatsapp:+34600000001")
    db.append_message(lead["id"], "user", "hola")
    db.append_message(lead["id"], "assistant", "respuesta")
    # No backdate: el last_contact_at es de hace segundos
    refreshed = db.list_leads()[0]
    assert _detect_returning_customer(refreshed) is None
