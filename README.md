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
| `app/main.py` | FastAPI + webhook Twilio (con validación de firma) + endpoints |
| `app/agent.py` | Bucle de conversación con Claude (tool use) + detección de cliente recurrente |
| `app/prompts.py` | Prompt de sistema de RAI + ejemplos few-shot |
| `app/tools.py` | Definición y despacho de herramientas |
| `app/pricing.py` | Motor de cálculo de horquilla de presupuesto |
| `app/kpis.py` | KPIs de la sección 11 del documento funcional |
| `app/db.py` | Persistencia SQLite (leads + transcripción) |
| `app/whatsapp.py` | Cliente Twilio WhatsApp |
| `app/handoff.py` | Escalado al instalador |
| `data/pricing.yaml` | Tabla de tarifas editable |
| `data/chargers.yaml` | Catálogo de cargadores |
| `data/subsidies.yaml` | Ayudas autonómicas por CP |
| `app/dashboard.html` | Dashboard visual servido en `/dashboard` |
| `app/auth.py` | Auth por API key para endpoints administrativos |
| `scripts/simulate.py` | CLI para probar el agente sin Twilio |
| `scripts/follow_up.py` | Seguimientos automáticos a 24h/3d/48h |
| `scripts/seed_demo_data.py` | Genera 5 leads de muestra para el dashboard |

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

Endpoints de inspección:

- `GET /dashboard` — UI web con KPIs en vivo, lista de leads y conversación
- `GET /leads` — lista todos los leads (JSON)
- `GET /leads/{id}/messages` — transcripción completa de un lead (JSON)
- `GET /kpis` — métricas agregadas, sección 11 del documento (JSON)

Para enseñar el dashboard sin tener que disparar conversaciones reales:

```bash
python scripts/seed_demo_data.py
uvicorn app.main:app --reload
# abre http://localhost:8000/dashboard
```

## Seguimiento automático

`scripts/follow_up.py` aplica las reglas de la sección 9:

| Estado | Tiempo sin respuesta | Acción |
| --- | --- | --- |
| incompleto | 24h | Enviar recordatorio amable |
| incompleto | 3 días | Enviar segundo recordatorio |
| incompleto | 7 días tras 2º recordatorio | Marcar `frio` + notificar instalador |
| cualificado | 48h tras oferta | Notificar instalador para llamada |

Ejecutar periódicamente (cron / systemd timer / n8n cada hora):

```bash
python scripts/follow_up.py            # ejecuta acciones
python scripts/follow_up.py --dry-run  # solo muestra qué haría
```

## Seguridad

**Webhook entrante**: el endpoint `/webhook/whatsapp` valida la firma `X-Twilio-Signature` con el `TWILIO_AUTH_TOKEN`. Si la cabecera falta o no coincide, devuelve `403`. Si `TWILIO_AUTH_TOKEN` no está configurado (dev), se omite la validación con warning.

**Endpoints administrativos**: `/dashboard`, `/leads`, `/leads/{id}/messages` y `/kpis` se protegen con `ADMIN_API_KEY` si está definido. Cliente puede enviarla por cabecera `X-Admin-API-Key: <clave>` o por query param `?key=<clave>`. Si `ADMIN_API_KEY` está vacío (dev), los endpoints son públicos.

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
