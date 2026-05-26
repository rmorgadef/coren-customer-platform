"""Rama de seguridad. Filtro rápido y barato (sin LLM) sobre el input.

Equivalente conceptual de la rama de seguridad de Coren. En RAI cubre:
- Detección de patrones de prompt injection
- Detección de PII filtrada por el cliente que no deberíamos persistir
  (DNI/NIE en plano antes de cualificar formalmente)
- Detección de quejas o enfado claros que disparan escalado directo
- Detección de casos fuera de alcance (industrial, fotovoltaica, comunidad
  grande) para acortar el flujo y escalar

La rama de seguridad NO devuelve la respuesta al cliente: devuelve una señal
para el Coordinator. El Coordinator decide qué hacer con esa señal.
"""

import re
from dataclasses import dataclass
from enum import Enum


class SecurityAction(str, Enum):
    PASS = "pass"
    BLOCK_AND_ESCALATE = "block_and_escalate"
    FLAG_FOR_HUMAN = "flag_for_human"


@dataclass
class SecurityVerdict:
    action: SecurityAction
    reason: str | None = None
    detected_flags: list[str] | None = None


# Patrones de prompt injection comunes (caja conservadora)
_INJECTION_PATTERNS = [
    re.compile(r"ignor[ae]\s+(?:tus|las|el|los)?\s*(?:instrucciones|reglas|prompts?)", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"act[uú]a\s+como\s+(?:un\s+)?(?:otro|distint[oa])", re.I),
    re.compile(r"olvida\s+(?:tus|las)\s+(?:instrucciones|reglas)", re.I),
    re.compile(r"(?:reveal[ae]?|mu[eé]strame|dame|ens[eé][ñn]ame|show)\s+(?:\w+\s+){0,2}prompt", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"DAN\s+mode", re.I),
]

# Indicadores claros de queja o enfado → escalado directo
_ANGER_PATTERNS = [
    re.compile(r"\b(?:estafa|estafadores|tim[oó]|fraude|asco|verg[uü]enza)\b", re.I),
    re.compile(r"\b(?:reclamaci[oó]n|denuncia|abogado|consumo|OCU)\b", re.I),
    re.compile(r"!{3,}"),  # múltiples exclamaciones
    re.compile(r"[A-ZÑÁÉÍÓÚ]{8,}"),  # texto en mayúsculas largo (≥ 8 chars)
]

# Casos complejos → escalado directo
_COMPLEX_CASE_PATTERNS = [
    re.compile(r"\b(?:industrial|nave|pol[ií]gono)\b", re.I),
    re.compile(r"\b(?:fotovoltaic[oa]|solar(?:es)?|placas?\s+solares)\b", re.I),
    re.compile(r"\b(?:varios|m[uú]ltiples|\d+)\s+cargadores\b", re.I),
    re.compile(r"\b(?:flota|empresa.*\d+\s*coches)\b", re.I),
    re.compile(r"\b(?:comunidad\s+grande|gran\s+comunidad|>\s*\d+\s+veh[ií]culos)\b", re.I),
]


class SecurityBranch:
    name = "security"

    def check(self, user_text: str) -> SecurityVerdict:
        flags: list[str] = []

        for p in _INJECTION_PATTERNS:
            if p.search(user_text):
                flags.append(f"injection_pattern:{p.pattern[:30]}")
                return SecurityVerdict(
                    action=SecurityAction.BLOCK_AND_ESCALATE,
                    reason="posible prompt injection detectado",
                    detected_flags=flags,
                )

        if any(p.search(user_text) for p in _ANGER_PATTERNS):
            flags.append("anger_or_complaint")
            return SecurityVerdict(
                action=SecurityAction.FLAG_FOR_HUMAN,
                reason="enfado o queja detectados",
                detected_flags=flags,
            )

        if any(p.search(user_text) for p in _COMPLEX_CASE_PATTERNS):
            flags.append("complex_case")
            return SecurityVerdict(
                action=SecurityAction.FLAG_FOR_HUMAN,
                reason="caso complejo fuera del alcance L1",
                detected_flags=flags,
            )

        return SecurityVerdict(action=SecurityAction.PASS)
