# RAI — Handoff & contexto del proyecto

Documento de traspaso para retomar trabajo en una nueva sesión Claude. Léelo entero antes de tocar código.

---

## TL;DR

**RAI** es un asistente conversacional para Raidasl (instalador de cargadores de coche eléctrico). Atiende leads por WhatsApp 24/7, los cualifica con 9 preguntas técnicas, calcula una horquilla de presupuesto y deriva al instalador humano. Esta es una **maqueta funcional Python** que espeja la arquitectura del repo TMF-Coders/coren-customer-platform (Coren AI Agentes).

Stack: **Python 3.11 + FastAPI + Twilio + Anthropic/OpenAI-compatible SDK + SQLite**. 7 commits, 37 tests pasando.

---

## Origen y decisión de stack

- La spec funcional la dio el cliente: **"RAI — Descripción Funcional v1.0 · Mayo 2026"**. Si la necesitas, está en el historial del chat original; los puntos clave están reflejados en código y en `app/prompts.py` (las 9 preguntas, reglas inviolables, RGPD, no MOVES III, etc).
- El repo Coren (`TMF-Coders/coren-customer-platform`) es **TypeScript** (Next.js + Express + Gemma4/Gemini + MCP a Libra + Qdrant + Vitest).
- **Se mantuvo Python a propósito**: el usuario dijo que el lenguaje no es relevante, solo replicar las "piezas arquitectónicas" (3-branch coordinator, circuit breaker, adapter LLM, RAG, ngrok+Twilio).

---

## Arquitectura (idéntica en patrón a Coren)

```
   ┌──────────────┐    ┌──────────────────┐    ┌────────────────────┐
   │  Seguridad   │ ║  │ Conversación/RAG │ ║  │   Transaccional    │
   │  (sin LLM:   │ ║  │ (BM25 sobre KB)  │ ║  │  (LLM + tools)     │
   │  regex)      │ ║  │                  │ ║  │                    │
   └──────┬───────┘ ║  └────────┬─────────┘ ║  └─────────┬──────────┘
          └─────────╨───────────┴───────────╨────────────┘
                              Coordinator
                                  │
                                  ▼
                          ┌───────────────┐
                          │ CircuitBreaker│  primary → fallback → heurística
                          └───────┬───────┘
                                  │
                ┌─────────────────┼───────────────────┐
                ▼                 ▼                   ▼
        Mistral Small         Mistral Medium       HeuristicFallback
        (Scaleway)            (Scaleway)           (degradación)
```

- **3 ramas en paralelo** (`ThreadPoolExecutor`): security + RAG arrancan a la vez. Su output condiciona la rama transaccional.
- **Security**: si detecta prompt injection → bloquea SIN llamar al LLM (ahorra tokens). Si detecta enfado/caso complejo → flag para que el LLM escale.
- **RAG**: recupera top-k docs de `data/knowledge.yaml` con BM25. Los inyecta en el system prompt.
- **Transactional**: bucle Claude/Mistral con 6 tools (cualificación, presupuesto, escalado, etc.).
- **CircuitBreaker**: timeout por llamada, opens tras N fallos, baja confianza → cae al fallback. Última red de seguridad es respuesta determinista + escalado.

---

## Estructura del repo

```
.
├── Makefile                    # install / test / dev / seed / simulate / follow-up
├── README.md
├── HANDOFF.md                  # este archivo
├── .env.example                # plantilla de configuración
├── apps/
│   ├── agent/                  # motor del agente
│   │   ├── app/
│   │   │   ├── main.py         # FastAPI: webhook Twilio + /dashboard + /kpis + /leads
│   │   │   ├── coordinator.py  # 3-branch orchestration
│   │   │   ├── circuit_breaker.py
│   │   │   ├── agent.py        # entry point (handle_user_message)
│   │   │   ├── prompts.py      # system prompt + 5 few-shot
│   │   │   ├── tools.py        # 6 tool defs + dispatcher
│   │   │   ├── pricing.py      # cálculo horquilla
│   │   │   ├── db.py           # SQLite (leads + messages)
│   │   │   ├── kpis.py         # endpoints de métricas
│   │   │   ├── auth.py         # API key para endpoints admin
│   │   │   ├── handoff.py      # notificación al instalador
│   │   │   ├── whatsapp.py     # cliente Twilio
│   │   │   ├── branches/
│   │   │   │   ├── security.py        # regex: prompt injection, enfado, casos complejos
│   │   │   │   ├── conversational.py  # wrapper del RAG
│   │   │   │   └── transactional.py   # bucle LLM + tools
│   │   │   ├── rag/
│   │   │   │   └── store.py    # BM25 in-memory (sustituible por Qdrant)
│   │   │   └── adapters/
│   │   │       └── llm/
│   │   │           ├── base.py              # interfaz LLMClient
│   │   │           ├── anthropic_client.py  # Claude
│   │   │           ├── ollama_client.py     # Gemma4/Llama/Qwen local
│   │   │           ├── openai_compatible.py # Scaleway, DeepSeek, etc.
│   │   │           ├── heuristic.py         # fallback determinista
│   │   │           └── factory.py           # monta primary + fallbacks desde .env
│   │   ├── data/
│   │   │   ├── pricing.yaml     # tabla tarifas editable
│   │   │   ├── chargers.yaml    # catálogo wallboxes
│   │   │   ├── subsidies.yaml   # ayudas autonómicas por CP
│   │   │   └── knowledge.yaml   # KB del RAG (IRPF, MOVES, permiso comunidad, etc.)
│   │   ├── scripts/
│   │   │   ├── simulate.py        # CLI sin Twilio
│   │   │   ├── seed_demo_data.py  # 5 leads de muestra para el dashboard
│   │   │   └── follow_up.py       # seguimientos 24h/3d/48h (cron job)
│   │   ├── tests/               # 37 tests pytest
│   │   └── requirements.txt
│   └── web-portal/
│       └── dashboard.html       # UI servida en /dashboard
└── docs/                        # vacío, pendiente de ADRs
```

---

## Configuración LLM por defecto (decisión clave)

```dotenv
LLM_PRIMARY=scaleway
LLM_FALLBACKS=scaleway

SCALEWAY_API_KEY=               # rellenar
SCALEWAY_BASE_URL=https://api.scaleway.ai/v1
SCALEWAY_MODEL=mistral-small-3.2-24b-instruct-2506
SCALEWAY_FALLBACK_MODEL=mistral-medium-3.5-128b
```

### Por qué Mistral en Scaleway

| Opción | Verdict |
|---|---|
| **Mistral Small (Scaleway París)** ✅ | **Elegido**. Soberanía EU, €0.15/M input + €0.35/M output, tool calling nativo, infra francesa, modelo francés. |
| Mistral Medium (Scaleway) | Fallback ideal: misma DPA, calidad superior. |
| Gemma 4 e4b on-prem (Ollama) | Alternativa válida si crece volumen → cambias `LLM_PRIMARY=ollama` y `OLLAMA_MODEL=gemma4:e4b`. Confirmado tool calling. Requiere GPU L4 24GB en Scaleway (~€450-600/mes). |
| Claude Sonnet/Haiku | Excelente calidad, NO soberano EU, más caro. Disponible vía `LLM_PRIMARY=anthropic`. |
| DeepSeek | Más barato pero API en China → RGPD problemático con datos personales. **Descartado para primary**, podría usarse solo como fallback. |

### Coste esperado para Raidasl
- ~1.000 leads/mes con Mistral Small: **~€3/mes**
- Si todo cayera al Medium (peor caso): **~€45/mes**
- VM con GPU (Gemma4 self-host) solo compensa a partir de ~33.000 conversaciones/mes — irrelevante para volumen de pyme regional.

---

## Cómo arrancarlo en local

```bash
make install           # pip install -r apps/agent/requirements.txt
cp .env.example .env   # rellenar SCALEWAY_API_KEY mínimo

# Probar sin Twilio (CLI interactivo)
make simulate

# Poblar BD con 5 leads de muestra para el dashboard
make seed

# Arrancar API (puerto 8000) — abre http://localhost:8000/dashboard
make dev

# Probar contra WhatsApp real:
# 1. Arrancar make dev
# 2. En otra terminal: ngrok http 8000
# 3. Pegar https://xxxx.ngrok-free.app/webhook/whatsapp en el sandbox de Twilio
# 4. Enviar `join <code>` al número Twilio desde tu móvil

# Tests
make test

# Seguimientos automáticos (cron job hourly)
make follow-up         # --dry-run por defecto
```

---

## Lo que está hecho

### Core funcional
- ✅ Atender entrante WhatsApp con webhook Twilio (validación firma)
- ✅ Las 9 preguntas técnicas de cualificación
- ✅ Cálculo horquilla presupuesto (tabla tarifas YAML editable)
- ✅ Lookup ayudas autonómicas por CP (estado open/closed/pending, sin cuantía)
- ✅ Save lead + handoff al instalador (log + webhook stub)
- ✅ Escalado por motivo (queja, caso complejo, postventa, etc.)
- ✅ Reconocimiento cliente recurrente (gap >60min con historial previo)
- ✅ Aviso RGPD en turno donde pide PII
- ✅ Sin MOVES III (cumple regla del spec)

### Arquitectura
- ✅ Monorepo apps/agent + apps/web-portal
- ✅ 3-branch coordinator paralelo
- ✅ Circuit breaker primary→fallback→heurística
- ✅ Adapters LLM: Anthropic, Ollama, OpenAI-compatible (sirve Scaleway, DeepSeek, etc.), Heuristic
- ✅ RAG: BM25 in-memory sobre `knowledge.yaml`
- ✅ Factory que monta la cadena desde `.env`

### Plataforma
- ✅ FastAPI + lifespan
- ✅ Dashboard HTML autocontenido (`/dashboard`) con KPIs en vivo, lista de leads, transcripción al click
- ✅ Endpoints admin protegidos con `ADMIN_API_KEY` (header `X-Admin-API-Key` o `?key=`)
- ✅ KPIs: totales, % por estado, motivos escalado, distribución CP/inmueble
- ✅ Seguimientos automáticos sección 9 spec (script + tabla `follow_ups` idempotente)
- ✅ Seed script para 5 leads de muestra

### Tests
- ✅ 37 tests pytest pasando:
  - pricing (8) — cálculo horquilla, lookup subsidios
  - auth (6) — endpoints admin protegidos
  - circuit breaker (7) — estados, fallback, timeout, low confidence
  - security branch (4) — injection, enfado, caso complejo
  - RAG (6) — recall de docs por query
  - kpis (2)
  - agent helpers (4) — detección cliente recurrente

---

## Lo que está pendiente (por prioridad)

### Alta — validar antes de cualquier prueba real
- [ ] **Verificar slugs/auth Scaleway**: la doc estaba bloqueada en la sesión cloud (no allowlist). Asumimos `https://api.scaleway.ai/v1` + `Authorization: Bearer` + slugs exactos de la página de pricing. Validar con `curl https://api.scaleway.ai/v1/models -H "Authorization: Bearer $SCW_SECRET_KEY"`. Si difiere, ajustar `app/config.py`.
- [ ] **Probar tool calling de Mistral Small** con nuestras 6 tools end-to-end. El bucle iterativo de tools necesita que el modelo devuelva `tool_calls` en formato OpenAI estándar; teóricamente Mistral lo soporta, hay que confirmar que respeta el schema JSON.
- [ ] **Probar conversación real end-to-end** con `make simulate` apuntando a Scaleway. Verificar calidad del español, calidad del tool calling, latencia.

### Media — completar la pieza arquitectónica de Coren
- [ ] **ADRs en `docs/adr/`**: documentar decisiones tomadas (3-branch coordinator, circuit breaker, modelo soberano EU, RAG BM25 vs Qdrant, sin GPU VM). Coren tiene esa carpeta; replicar.
- [ ] **Runbook ngrok + Twilio sandbox** en `docs/runbooks/`: setup paso a paso para F&F testing.
- [ ] **Observabilidad estructurada**: logs JSON con `request_id`, `lead_id`, `branch`, `latency_ms`, `model_used`. Ahora hay `logging.info` sueltos. Para producción, integrar con un sink (Scaleway Cockpit, Grafana Loki).
- [ ] **Tests end-to-end con LLM mock**: actualmente los tests no cubren el bucle completo del Coordinator porque ese sí llama al LLM. Mockear con un `LLMClient` stub que devuelva tool_uses prefabricados.

### Baja — mejoras
- [ ] **Validación de firma Twilio**: ya está, pero faltan tests del endpoint con firma válida/inválida.
- [ ] **Ampliar knowledge.yaml**: ahora son 9 docs. Para coberttura real de FAQ, llegar a 30-50.
- [ ] **Adapter MCP-style para CRM del instalador**: el `handoff.py` actual es un log+webhook. Coren usa MCP Protocol hacia Libra; aquí podríamos definir un adapter limpio (interfaz `CRMClient` con `notify_lead`, `get_lead`, `update_status`).
- [ ] **Embeddings reales para RAG**: BM25 cubre 95% del caso pero si la KB crece >100 docs, considerar Qdrant + `qwen3-embedding-8b` (Scaleway lo tiene a €0.10/M tokens).
- [ ] **Modo "primary multimodal"**: aprovechar que Mistral Small soporta vision para futuro "envíame foto de tu cuadro eléctrico".

---

## Constraints conocidos importantes

1. **Esto es una maqueta/POC**, no producción. Hay decisiones explícitamente "buenas para demo" (SQLite en disco, BM25 en memoria, knowledge.yaml estático, follow-up script en cron en vez de worker). Cuando vaya a prod, sustituir SQLite por Postgres en Scaleway, follow-up por queue (n8n/Celery), KB por Qdrant con embeddings.

2. **Coren está en TS, no Python**. Si en algún momento quieres "fusionar" con el monorepo de Coren, hay que portar (o convivir como microservicios separados detrás del mismo BFF Express).

3. **Webhook Twilio**: respondemos vía outbound API (no TwiML inline) porque permite respuestas largas y multi-turno. El webhook devuelve `<Response/>` vacío.

4. **PII y RGPD**: el aviso RGPD se inyecta al pedir nombre/email. Los datos viven en SQLite local (en prod: Postgres Scaleway París). DeepSeek queda descartado como primary precisamente por esto.

---

## Decisiones tomadas y por qué (decisiones reversibles si cambia el contexto)

| Decisión | Razón |
|---|---|
| Python en vez de TS | Usuario lo confirmó; el valor está en la arquitectura, no en el lenguaje. Más cómodo iterar agente con Python+Anthropic SDK. |
| FastAPI vs Express | Equivalente funcional al BFF de Coren. Lifespan en vez de on_event deprecado. |
| SQLite vs Postgres | Maqueta. En prod: Postgres Scaleway París. Migración trivial, capa db.py aislada. |
| BM25 vs Qdrant | Maqueta + KB pequeña. El módulo `rag/store.py` se sustituye manteniendo interfaz `retrieve(query, k) -> list[Doc]`. |
| Mistral Small primary | Soberanía EU + tool calling + precio + Scaleway París cubre el "datos en EU" del spec. |
| Mistral Medium fallback | Misma DPA, calidad superior. Activado por circuit breaker solo en fallos. |
| Heurística como último fallback | Garantiza respuesta + escalado incluso si Mistral está caído. |
| Lifecycle del coordinator: singleton lazy | Una instancia por proceso. Se reusa entre requests. Thread-safe (tools dispatch usa connection-per-call). |
| RAG en paralelo con Security | Latencia: el coste extra del RAG se solapa con la latencia de red del LLM. |
| Security branch sin LLM | Detecta los 3 casos comunes (injection / enfado / caso complejo) sin pagar tokens. Para el resto, el system prompt + tools del LLM hacen el trabajo. |

---

## Rama y commits

Rama actual: `claude/rai-whatsapp-demo-CpE1i`. Commits (más reciente arriba):

1. Default a Scaleway Mistral Small/Medium (soberano EU)
2. Fijar Gemma 4 e4b como default Ollama y documentar variantes
3. Refactor a monorepo + 3-branch coordinator + circuit breaker
4. Dashboard HTML + API key auth + seed script + lifespan
5. Follow-up + KPIs + cliente recurrente + Twilio signature
6. Initial RAI WhatsApp assistant demo

---

## Siguiente acción recomendada

1. `cp .env.example .env`
2. Rellena `SCALEWAY_API_KEY=...`
3. `curl https://api.scaleway.ai/v1/models -H "Authorization: Bearer $SCALEWAY_API_KEY" | jq` para confirmar slugs
4. `make install && make seed && make dev`
5. Abre `http://localhost:8000/dashboard` para ver los 5 leads de muestra
6. `make simulate` para probar una conversación end-to-end vs Scaleway real
7. Si todo OK → atacar la lista de "Pendientes prioritarios alta"
