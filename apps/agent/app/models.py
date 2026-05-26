from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LeadStatus(str, Enum):
    INCOMPLETO = "incompleto"
    CUALIFICADO = "cualificado"
    ESCALADO = "escalado"
    FRIO = "frio"
    CERRADO = "cerrado"


class PropertyType(str, Enum):
    UNIFAMILIAR = "unifamiliar"
    PISO_EDIFICIO = "piso_edificio"
    COMUNIDAD = "comunidad"
    EMPRESA = "empresa"


class Supply(str, Enum):
    MONOFASICO = "monofasico"
    TRIFASICO = "trifasico"


class QualificationAnswers(BaseModel):
    """Las 9 preguntas del documento funcional, sección 4.3."""

    property_type: Optional[PropertyType] = None
    parking_location: Optional[str] = Field(
        None, description="misma finca | parking externo | calle"
    )
    garage_level: Optional[str] = Field(
        None, description="planta_baja | -1 | -2 | -3 | -4"
    )
    distance_meters_range: Optional[str] = Field(
        None, description="<10 | 10-25 | 25-50 | >50"
    )
    contracted_power_kw: Optional[float] = None
    supply: Optional[Supply] = None
    vehicle_model: Optional[str] = None
    community_permission: Optional[bool] = None
    postal_code: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None


class QuoteEstimate(BaseModel):
    charger_id: str
    charger_name: str
    price_low: float
    price_high: float
    install_hours: int
    breakdown: dict[str, float]
    irpf_deduction_pct: float = 15.0
    irpf_deduction_note: str = (
        "Deducción del 15% en IRPF aplicable en la siguiente declaración. "
        "No se descuenta del presupuesto, es ahorro fiscal posterior."
    )
    regional_subsidy_status: str = "unknown"
    regional_subsidy_note: Optional[str] = None
