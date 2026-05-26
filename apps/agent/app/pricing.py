from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from app.models import QuoteEstimate


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def _pricing() -> dict:
    return yaml.safe_load((DATA_DIR / "pricing.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _chargers() -> dict:
    return yaml.safe_load((DATA_DIR / "chargers.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _subsidies() -> dict:
    return yaml.safe_load((DATA_DIR / "subsidies.yaml").read_text(encoding="utf-8"))


DISTANCE_MIDPOINT = {
    "<10": 8,
    "10-25": 18,
    "25-50": 38,
    ">50": 65,
}


def recommend_charger(vehicle_model: Optional[str], supply: str) -> dict:
    """Heurística simple: con monofásico va el 7.4 kW; con trifásico el 11 kW por defecto.
    El 22 kW solo si el usuario lo pide explícitamente — no se recomienda solo."""
    if supply == "monofasico":
        target_id = "wallbox_7_4kw_mono"
    else:
        target_id = "wallbox_11kw_tri"
    for c in _chargers()["recommendations"]:
        if c["id"] == target_id:
            return c
    raise ValueError(f"No se encontró cargador {target_id}")


def lookup_subsidy(postal_code: str) -> dict:
    """Devuelve estado de ayudas autonómicas para un CP. Nunca cuantía."""
    subs = _subsidies()
    prefix = (postal_code or "")[:2]
    region_key = subs["cp_to_region"].get(prefix)
    if not region_key:
        return {"status": "unknown", "region": None, "note": None}
    region = subs["regions"].get(region_key, {})
    return {
        "status": region.get("status", "unknown"),
        "region": region.get("name"),
        "note": region.get("note"),
    }


def calculate_quote(
    property_type: str,
    supply: str,
    distance_range: str,
    garage_level: str,
    vehicle_model: Optional[str],
    postal_code: Optional[str],
) -> QuoteEstimate:
    p = _pricing()

    charger = recommend_charger(vehicle_model, supply)
    charger_price = p["chargers"][charger["id"]]

    install_base = p["installation_base"][property_type]
    meters = DISTANCE_MIDPOINT.get(distance_range, 18)
    cable_cost = meters * p["cable_per_meter"][supply]
    garage_level_key = garage_level if garage_level in p["garage_level_surcharge"] else "planta_baja"
    garage_surcharge = p["garage_level_surcharge"][garage_level_key]
    protections = p["electrical_protections"][supply]

    base = charger_price + install_base + cable_cost + garage_surcharge + protections

    spread = p["spread_pct"] / 100.0
    price_low = round(base * (1 - spread), -1)
    price_high = round(base * (1 + spread), -1)

    breakdown = {
        "cargador": charger_price,
        "mano_obra_base": install_base,
        "cable_y_canaleta": round(cable_cost, 2),
        "suplemento_planta": garage_surcharge,
        "protecciones_electricas": protections,
    }

    subsidy = lookup_subsidy(postal_code or "")

    return QuoteEstimate(
        charger_id=charger["id"],
        charger_name=charger["name"],
        price_low=price_low,
        price_high=price_high,
        install_hours=p["install_hours"][property_type],
        breakdown=breakdown,
        regional_subsidy_status=subsidy["status"],
        regional_subsidy_note=(
            f"{subsidy['region']}: {subsidy['note']}" if subsidy["region"] and subsidy["note"]
            else (subsidy["region"] if subsidy["region"] else None)
        ),
    )
