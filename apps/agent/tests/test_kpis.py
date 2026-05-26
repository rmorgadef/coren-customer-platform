"""Tests del módulo de KPIs (sección 11 documento funcional)."""

import os
import tempfile

import pytest

from app import db
from app.kpis import compute_kpis


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(db.settings, "database_path", path)
    db.init_db()
    yield
    os.unlink(path)


def test_kpis_empty():
    k = compute_kpis()
    assert k["leads_total"] == 0
    assert k["pct_cualificados"] == 0.0


def test_kpis_with_leads():
    l1 = db.get_or_create_lead("whatsapp:+34600000001")
    db.update_lead_answers(l1["id"], {"property_type": "unifamiliar", "postal_code": "28001"})
    db.set_lead_quote(l1["id"], {"price_low": 1300, "price_high": 1800})

    l2 = db.get_or_create_lead("whatsapp:+34600000002")
    db.escalate_lead(l2["id"], "postventa_o_incidencia: cargador roto")

    l3 = db.get_or_create_lead("whatsapp:+34600000003")
    db.update_lead_answers(l3["id"], {"property_type": "piso_edificio", "postal_code": "08001"})

    k = compute_kpis()
    assert k["leads_total"] == 3
    assert k["leads_por_estado"]["cualificado"] == 1
    assert k["leads_por_estado"]["escalado"] == 1
    assert k["leads_por_estado"]["incompleto"] == 1
    assert k["pct_cualificados"] == pytest.approx(33.3, abs=0.1)
    assert "postventa_o_incidencia" in k["motivos_escalado"]
    assert k["distribucion_cp_prefijo"]["28"] == 1
    assert k["distribucion_cp_prefijo"]["08"] == 1
    assert k["distribucion_tipo_inmueble"]["unifamiliar"] == 1
    assert k["distribucion_tipo_inmueble"]["piso_edificio"] == 1
