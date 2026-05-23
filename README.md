# RAI — Asistente virtual de Raidasl (Demo)

Maqueta funcional del asistente conversacional **RAI** para Raidasl: atiende leads de instalación de cargadores de coche eléctrico por WhatsApp, los cualifica con 9 preguntas técnicas, calcula una horquilla estimada de presupuesto y deriva al instalador humano.

> Esta es una **demo / prueba de concepto**. No tiene pretensión de ser producción.
> Cumple con lo descrito en la "Descripción Funcional RAI v1.0 · Mayo 2026".

---

## Arquitectura

```
WhatsApp (Twilio Sandbox)
        │
        ▼
   ngrok tunnel
        │
        ▼
   FastAPI webhook  ──►  Claude (Anthropic SDK)
        │                      │
        │                  tool_use:
        │                  - ask_question
        │                  - calculate_quote
        │                  - lookup_subsidies
        │                  - save_lead
        │                  - escalate_to_human
        ▼
   SQLite (leads, conversations, messages)
        │
        ▼
   Handoff (log / webhook stub al instalador)
```

Componentes:

| Módulo | Responsabilidad |
| --- | --- |
| `app/main.py` | FastAPI + endpoint Twilio webhook |
| `app/agent.py` | Bucle de conversación con Claude (tool use) |
| `app/prompts.py` | Prompt de sistema de RAI |
| `app/tools.py` | Definición y despacho de herramientas |
| `app/pricing.py` | Motor de cálculo de horquilla de presupuesto |
| `app/db.py` | Persistencia SQLite (leads + transcripción) |
| `app/whatsapp.py` | Cliente Twilio WhatsApp |
| `app/handoff.py` | Escalado al instalador |
| `data/pricing.yaml` | Tabla de tarifas editable |
| `data/chargers.yaml` | Catálogo de cargadores |
| `data/subsidies.yaml` | Ayudas autonómicas por CP |
| `scripts/simulate.py` | CLI para probar el agente sin Twilio |

---

## Puesta en marcha (local, F&F testing)

### 1. Requisitos

- Python 3.11+
- Cuenta Twilio con WhatsApp Sandbox activado
- API key de Anthropic
- ngrok instalado

### 2. Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edita .env con tus credenciales
```

### 3. Probar el agente sin Twilio (CLI)

```bash
python scripts/simulate.py
```

Abre una conversación interactiva con RAI en la terminal. Útil para iterar prompts sin pasar por WhatsApp.

### 4. Probar end-to-end con WhatsApp + ngrok

```bash
# Terminal 1: API
uvicorn app.main:app --reload --port 8000

# Terminal 2: túnel
ngrok http 8000
```

Pega la URL `https://xxxx.ngrok-free.app/webhook/whatsapp` en la configuración del WhatsApp Sandbox de Twilio (campo "WHEN A MESSAGE COMES IN").

Une tu móvil al sandbox enviando el `join <code>` desde WhatsApp al número de Twilio, y empieza a hablar con RAI.

---

## Estado del lead

Cada conversación produce un lead con uno de estos estados:

- `incompleto` — no terminó las 9 preguntas
- `cualificado` — completó cualificación + horquilla generada
- `escalado` — derivado a humano (motivo registrado)
- `frio` — sin respuesta tras 2 recordatorios

Consultable vía `GET /leads` o directamente en `data/rai.db`.

---

## Qué hace y qué NO hace (recordatorio)

**Sí:** atiende 24/7, cualifica, da horquilla, menciona deducción 15% IRPF 2026, captura datos, escala.

**No:** cierra venta, da precio cerrado, compromete fechas, gestiona postventa, promete subvenciones.

---

## Próximos pasos para producción

- Sustituir SQLite por Postgres en Scaleway (París)
- Mover prompts a un sistema versionado con rollback
- Integrar n8n para los flujos de seguimiento (24h, 3 días, 48h post-oferta)
- Logging estructurado y dashboard de KPIs
- Aviso RGPD con enlace a política de privacidad real
- Autenticación de webhook (validar firma Twilio)
