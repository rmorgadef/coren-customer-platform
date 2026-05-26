"""Genera 5 leads de muestra para enseñar el dashboard sin tener que
disparar conversaciones reales por WhatsApp.

Uso:
    python scripts/seed_demo_data.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db


SAMPLES = [
    {
        "phone": "whatsapp:+34611111001",
        "name": "María García",
        "email": "maria@example.com",
        "status": "cualificado",
        "answers": {
            "property_type": "unifamiliar",
            "postal_code": "28015",
            "vehicle_model": "Tesla Model 3",
            "supply": "trifasico",
            "garage_level": "planta_baja",
            "distance_meters_range": "<10",
        },
        "quote": {
            "price_low": 2180,
            "price_high": 2950,
            "charger_name": "Wallbox 11 kW trifásico",
            "install_hours": 4,
        },
        "transcript": [
            ("user", "Hola, quiero un cargador para mi Tesla"),
            ("assistant", "¡Hola! Soy RAI, asistente virtual automatizado de Raidasl..."),
        ],
    },
    {
        "phone": "whatsapp:+34611111002",
        "name": "Juan Pérez",
        "email": "juan@example.com",
        "status": "cualificado",
        "answers": {
            "property_type": "piso_edificio",
            "postal_code": "08023",
            "vehicle_model": "Renault Zoe",
            "supply": "monofasico",
            "garage_level": "-2",
            "distance_meters_range": "25-50",
        },
        "quote": {
            "price_low": 1850,
            "price_high": 2500,
            "charger_name": "Wallbox 7,4 kW monofásico",
            "install_hours": 6,
        },
        "transcript": [
            ("user", "necesito presupuesto para mi plaza de garaje"),
            ("assistant", "¡Hola! Soy RAI, te ayudo en un par de minutos..."),
        ],
    },
    {
        "phone": "whatsapp:+34611111003",
        "name": "Ana López",
        "email": None,
        "status": "incompleto",
        "answers": {"property_type": "piso_edificio", "postal_code": "28041"},
        "quote": None,
        "transcript": [
            ("user", "hola, info cargadores"),
            ("assistant", "¡Hola! Soy RAI... ¿dónde se instalaría?"),
            ("user", "piso en madrid"),
            ("assistant", "Perfecto. ¿En qué planta está tu plaza de garaje?"),
        ],
    },
    {
        "phone": "whatsapp:+34611111004",
        "name": None,
        "email": None,
        "status": "incompleto",
        "answers": {},
        "quote": None,
        "transcript": [
            ("user", "buenas, una pregunta rapida"),
        ],
    },
    {
        "phone": "whatsapp:+34611111005",
        "name": "Carlos Ruiz",
        "email": "carlos@empresa.com",
        "status": "escalado",
        "answers": {"property_type": "empresa", "postal_code": "46010"},
        "quote": None,
        "escalation_reason": "caso_complejo: instalación industrial 5 cargadores + integración fotovoltaica",
        "transcript": [
            ("user", "Necesito 5 cargadores en la oficina y queremos integrarlos con paneles solares"),
            ("assistant", "Eso es justo el tipo de caso que paso directamente a un compañero técnico..."),
        ],
    },
]


def main() -> int:
    db.init_db()
    for s in SAMPLES:
        lead = db.get_or_create_lead(s["phone"])
        for role, content in s["transcript"]:
            db.append_message(lead["id"], role, content)
        if s["answers"]:
            db.update_lead_answers(lead["id"], s["answers"])
        if s["name"] or s["email"]:
            db.set_lead_contact(lead["id"], s["name"], s["email"])
        if s["quote"]:
            db.set_lead_quote(lead["id"], s["quote"])
        if s["status"] == "escalado":
            db.escalate_lead(lead["id"], s["escalation_reason"])
    print(f"OK — {len(SAMPLES)} leads de muestra creados en {db.settings.database_path}")
    print("Abre el dashboard en http://localhost:8000/dashboard tras lanzar uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
