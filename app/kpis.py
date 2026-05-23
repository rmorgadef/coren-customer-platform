"""KPIs de la sección 11 del documento funcional.

Calcula sobre los datos en SQLite. Para producción esto vivirá en un dashboard
con agregaciones más sofisticadas (medias por ventana de tiempo, percentiles).
"""

from collections import Counter
from datetime import datetime
from typing import Optional

from app import db


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _seconds_between(a: Optional[str], b: Optional[str]) -> Optional[float]:
    da, db_ = _parse(a), _parse(b)
    if not da or not db_:
        return None
    return (db_ - da).total_seconds()


def compute_kpis() -> dict:
    leads = db.list_leads()
    total = len(leads)

    status_counts = Counter(l["status"] for l in leads)
    cualificados = status_counts.get("cualificado", 0)
    incompletos = status_counts.get("incompleto", 0)
    escalados = status_counts.get("escalado", 0)

    qualification_seconds: list[float] = []
    first_response_seconds: list[float] = []
    cp_distribution = Counter()
    property_distribution = Counter()
    escalation_reasons = Counter()

    for lead in leads:
        msgs = db.get_messages(lead["id"])
        first_user_msg = next((m for m in msgs if m["role"] == "user"), None)
        first_assistant_msg = next((m for m in msgs if m["role"] == "assistant"), None)

        # Tiempo medio de primera respuesta
        if first_user_msg and first_assistant_msg:
            # En la maqueta no almacenamos created_at por mensaje individual exacto,
            # usamos first_contact_at del lead como proxy del primer user message.
            # Para mayor precisión, ampliar el esquema messages.created_at.
            pass

        # Tiempo total de cualificación (primer contacto → estado cualificado)
        if lead["status"] == "cualificado":
            secs = _seconds_between(lead["first_contact_at"], lead["last_contact_at"])
            if secs is not None:
                qualification_seconds.append(secs)

        answers = db.get_lead_answers(lead["id"])
        if cp := answers.get("postal_code"):
            cp_distribution[cp[:2]] += 1
        if pt := answers.get("property_type"):
            property_distribution[pt] += 1

        if lead["status"] == "escalado" and (reason := lead.get("escalation_reason")):
            base_reason = reason.split(":", 1)[0]
            escalation_reasons[base_reason] += 1

    avg_qualification_seconds = (
        sum(qualification_seconds) / len(qualification_seconds)
        if qualification_seconds
        else None
    )

    pct = lambda n: round(100 * n / total, 1) if total else 0.0

    return {
        "leads_total": total,
        "leads_por_estado": dict(status_counts),
        "pct_cualificados": pct(cualificados),
        "pct_incompletos": pct(incompletos),
        "pct_escalados": pct(escalados),
        "tiempo_medio_cualificacion_segundos": (
            round(avg_qualification_seconds, 1) if avg_qualification_seconds else None
        ),
        "motivos_escalado": dict(escalation_reasons),
        "distribucion_cp_prefijo": dict(cp_distribution.most_common(10)),
        "distribucion_tipo_inmueble": dict(property_distribution),
    }
