"""Tests del motor de pricing y lookup de subvenciones.

Ejecutar con: python -m pytest tests/ -v
"""

from app.pricing import calculate_quote, lookup_subsidy, recommend_charger


def test_recommend_charger_monofasico():
    c = recommend_charger("Renault Zoe", "monofasico")
    assert c["id"] == "wallbox_7_4kw_mono"


def test_recommend_charger_trifasico_defaults_to_11kw():
    c = recommend_charger("Tesla Model 3", "trifasico")
    assert c["id"] == "wallbox_11kw_tri"


def test_quote_unifamiliar_monofasico():
    q = calculate_quote(
        property_type="unifamiliar",
        supply="monofasico",
        distance_range="<10",
        garage_level="planta_baja",
        vehicle_model="Renault Zoe",
        postal_code="28001",
    )
    assert q.charger_id == "wallbox_7_4kw_mono"
    assert q.price_low < q.price_high
    assert q.install_hours == 4
    assert "cargador" in q.breakdown
    assert q.irpf_deduction_pct == 15.0


def test_quote_piso_edificio_trifasico_subterraneo():
    q = calculate_quote(
        property_type="piso_edificio",
        supply="trifasico",
        distance_range="25-50",
        garage_level="-2",
        vehicle_model="Tesla Model Y",
        postal_code="08001",
    )
    assert q.charger_id == "wallbox_11kw_tri"
    # Es claramente más caro que un unifamiliar plano
    cheap = calculate_quote(
        property_type="unifamiliar",
        supply="monofasico",
        distance_range="<10",
        garage_level="planta_baja",
        vehicle_model="Renault Zoe",
        postal_code="28001",
    )
    assert q.price_low > cheap.price_low


def test_quote_horquilla_es_simetrica():
    q = calculate_quote(
        property_type="unifamiliar",
        supply="monofasico",
        distance_range="<10",
        garage_level="planta_baja",
        vehicle_model="Renault Zoe",
        postal_code="28001",
    )
    mid = (q.price_low + q.price_high) / 2
    spread = (q.price_high - q.price_low) / 2
    # spread del 15% sobre el mid, con tolerancia por el redondeo a la decena
    assert abs(spread / mid - 0.15) < 0.02


def test_subsidy_madrid():
    s = lookup_subsidy("28001")
    assert s["region"] == "Comunidad de Madrid"


def test_subsidy_cataluna_open():
    s = lookup_subsidy("08001")
    assert s["region"] == "Cataluña"
    assert s["status"] == "open"


def test_subsidy_unknown_cp():
    s = lookup_subsidy("99999")
    assert s["status"] == "unknown"
    assert s["region"] is None
