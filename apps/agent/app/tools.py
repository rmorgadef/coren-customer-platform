"""Tool definitions for the Claude agent + dispatcher.

Each tool has:
- a JSON schema in TOOL_SPECS (sent to the model)
- a Python handler in TOOL_HANDLERS (executed when the model calls it)
"""

from typing import Any

from app import db
from app.handoff import notify_installer
from app.pricing import calculate_quote as _calculate_quote
from app.pricing import lookup_subsidy


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "update_qualification",
        "description": (
            "Registra una o más respuestas del cliente a las 9 preguntas de cualificación. "
            "Llámala SIEMPRE tras validar una respuesta antes de pasar a la siguiente pregunta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_type": {
                    "type": "string",
                    "enum": ["unifamiliar", "piso_edificio", "comunidad", "empresa"],
                },
                "parking_location": {"type": "string"},
                "garage_level": {
                    "type": "string",
                    "enum": ["planta_baja", "-1", "-2", "-3", "-4"],
                },
                "distance_meters_range": {
                    "type": "string",
                    "enum": ["<10", "10-25", "25-50", ">50"],
                },
                "contracted_power_kw": {"type": "number"},
                "supply": {"type": "string", "enum": ["monofasico", "trifasico"]},
                "vehicle_model": {"type": "string"},
                "community_permission": {"type": "boolean"},
                "postal_code": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "lookup_subsidy_status",
        "description": (
            "Consulta si existen ayudas autonómicas vigentes para un código postal. "
            "Devuelve solo el estado (open/closed/pending/unknown), nunca cuantías."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "postal_code": {"type": "string", "description": "Código postal español de 5 dígitos"},
            },
            "required": ["postal_code"],
        },
    },
    {
        "name": "calculate_quote",
        "description": (
            "Calcula la horquilla estimada de presupuesto. Solo llamar cuando tengas "
            "property_type, supply, distance_meters_range, garage_level, vehicle_model y postal_code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "property_type": {
                    "type": "string",
                    "enum": ["unifamiliar", "piso_edificio", "comunidad", "empresa"],
                },
                "supply": {"type": "string", "enum": ["monofasico", "trifasico"]},
                "distance_meters_range": {
                    "type": "string",
                    "enum": ["<10", "10-25", "25-50", ">50"],
                },
                "garage_level": {
                    "type": "string",
                    "enum": ["planta_baja", "-1", "-2", "-3", "-4"],
                },
                "vehicle_model": {"type": "string"},
                "postal_code": {"type": "string"},
            },
            "required": [
                "property_type",
                "supply",
                "distance_meters_range",
                "garage_level",
                "vehicle_model",
                "postal_code",
            ],
        },
    },
    {
        "name": "save_lead",
        "description": "Guarda nombre y email del cliente en el CRM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
            },
            "required": ["name", "email"],
        },
    },
    {
        "name": "notify_installer_handoff",
        "description": (
            "Notifica al instalador humano que el lead está listo para tomar el relevo. "
            "Llamar al cerrar conversación cualificada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Resumen breve del lead para el instalador (1-2 frases)",
                },
            },
            "required": ["summary"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Marca el lead como escalado y notifica al instalador. "
            "Usar cuando el cliente lo pida, haya enfado/queja, caso complejo, postventa, "
            "o conversación atascada."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": [
                        "cliente_lo_pide",
                        "caso_complejo",
                        "postventa_o_incidencia",
                        "enfado_o_frustracion",
                        "duda_legal_o_fiscal",
                        "atascada",
                    ],
                },
                "note": {"type": "string", "description": "Contexto adicional para el instalador"},
            },
            "required": ["reason"],
        },
    },
]


def dispatch_tool(name: str, args: dict, *, lead_id: int, phone: str) -> dict:
    """Ejecuta una tool y devuelve el resultado serializable que se envía al modelo."""

    if name == "update_qualification":
        current = db.get_lead_answers(lead_id)
        current.update({k: v for k, v in args.items() if v is not None})
        db.update_lead_answers(lead_id, current)
        return {"ok": True, "answers": current}

    if name == "lookup_subsidy_status":
        result = lookup_subsidy(args["postal_code"])
        return result

    if name == "calculate_quote":
        quote = _calculate_quote(
            property_type=args["property_type"],
            supply=args["supply"],
            distance_range=args["distance_meters_range"],
            garage_level=args["garage_level"],
            vehicle_model=args.get("vehicle_model"),
            postal_code=args.get("postal_code"),
        )
        quote_dict = quote.model_dump()
        db.set_lead_quote(lead_id, quote_dict)
        return quote_dict

    if name == "save_lead":
        db.set_lead_contact(lead_id, args.get("name"), args.get("email"))
        current = db.get_lead_answers(lead_id)
        current["contact_name"] = args.get("name")
        current["contact_email"] = args.get("email")
        db.update_lead_answers(lead_id, current)
        return {"ok": True}

    if name == "notify_installer_handoff":
        answers = db.get_lead_answers(lead_id)
        leads = [l for l in db.list_leads() if l["id"] == lead_id]
        lead = leads[0] if leads else {}
        quote_json = lead.get("quote_json")
        import json as _json
        quote = _json.loads(quote_json) if quote_json else None
        transcript = "\n".join(
            f"{m['role']}: {m['content']}" for m in db.get_messages(lead_id)[-10:]
        )
        notify_installer(
            lead_id=lead_id,
            phone=phone,
            name=lead.get("name"),
            email=lead.get("email"),
            reason="lead_cualificado: " + args.get("summary", ""),
            answers=answers,
            quote=quote,
            transcript_excerpt=transcript,
        )
        return {"ok": True}

    if name == "escalate_to_human":
        reason = args["reason"]
        note = args.get("note", "")
        db.escalate_lead(lead_id, f"{reason}: {note}" if note else reason)
        answers = db.get_lead_answers(lead_id)
        leads = [l for l in db.list_leads() if l["id"] == lead_id]
        lead = leads[0] if leads else {}
        transcript = "\n".join(
            f"{m['role']}: {m['content']}" for m in db.get_messages(lead_id)[-10:]
        )
        notify_installer(
            lead_id=lead_id,
            phone=phone,
            name=lead.get("name"),
            email=lead.get("email"),
            reason=f"escalado:{reason} - {note}",
            answers=answers,
            quote=None,
            transcript_excerpt=transcript,
        )
        return {"ok": True, "escalated": True}

    return {"error": f"Tool desconocida: {name}"}
