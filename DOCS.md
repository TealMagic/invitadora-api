# Invitadora API — Documentación

API para enviar invitaciones WhatsApp con template aprobado, QR por destinatario y procesamiento asíncrono.

**Producción:** `https://api-production-a4cb.up.railway.app`  
**OpenAPI interactivo:** `/docs` y `/openapi.json`

---

## Autenticación

Todos los endpoints bajo `/v1` requieren header:

```http
X-API-Key: <INTERNAL_API_KEY>
```

Excepciones públicas (sin API key):

- `GET /health`, `GET /ready`
- `GET /qrs/{campaign_id}/{recipient_id}.jpg` (WhatsApp/Meta descarga el QR)

---

## Flujo típico

```text
1. POST /v1/campaigns              → crear campaña
2. POST /v1/campaigns/{id}/import-recipients → cargar invitados (JSON)
3. POST /v1/campaigns/{id}/dispatch    → encolar envío
4. GET  /v1/campaigns/{id}/stats      → polling de progreso
5. GET  /v1/campaigns/{id}/recipients  → detalle por destinatario
```

> **Deprecated:** `POST /v1/campaigns/{id}/import-file` (CSV) sigue disponible por compatibilidad pero se recomienda usar `import-recipients`.

El envío real lo procesa un **worker** en background. La API responde rápido y no bloquea mientras mandan los mensajes.

---

## Endpoints

### Salud

#### `GET /health`

Estado general y conexión a base de datos.

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "production",
  "database": "connected"
}
```

#### `GET /ready`

Readiness para deploy. Responde `503` si la DB no está lista.

---

### Campañas

#### `POST /v1/campaigns`

Crea una campaña en estado `draft`.

**Body (JSON):**

```json
{
  "organizer_name": "Tomás",
  "event_at": "2026-12-12T21:00:00-03:00",
  "template_name": "confirmacion_registro",
  "template_language": "es_CL",
  "created_by": "webapp-opcional"
}
```

| Campo | Requerido | Default |
|-------|-----------|---------|
| `organizer_name` | sí | — |
| `event_at` | sí | ISO 8601 con timezone |
| `template_name` | no | `confirmacion_registro` |
| `template_language` | no | `es_CL` |
| `created_by` | no | `null` |

**Respuesta `201`:** objeto campaña con `id`, `status`, contadores en cero.

---

#### `GET /v1/campaigns/{campaign_id}`

Detalle de la campaña.

---

#### `GET /v1/campaigns/{campaign_id}/stats`

Métricas para barra de progreso.

```json
{
  "campaign_id": "uuid",
  "status": "processing",
  "total_rows": 7,
  "total_unique_recipients": 1,
  "total_sent": 0,
  "total_failed": 0,
  "total_invalid": 0,
  "pending": 1,
  "processing": 0
}
```

---

#### `POST /v1/campaigns/{campaign_id}/import-recipients`

Importa invitados desde JSON. **No envía mensajes.** Reemplaza el draft anterior (`mode: replace`).

**Content-Type:** `application/json`

**Body:**

```json
{
  "recipients": [
    {
      "display_name": "Juan Pérez",
      "button_phone": "+5491155551234",
      "entry_code": "ENT-A3B7K"
    }
  ],
  "mode": "replace"
}
```

| Campo | Requerido | Descripción |
|-------|-----------|-------------|
| `recipients` | sí | Lista de invitados (mín. 1) |
| `recipients[].display_name` | sí | Nombre del invitado |
| `recipients[].button_phone` | sí | Teléfono; misma normalización AR que CSV |
| `recipients[].entry_code` | no | Código de entrada/check-in; si falta, se genera al enviar |
| `mode` | no | Solo `"replace"` (default) |

**Reglas:**

- Varios invitados con el mismo teléfono se agrupan en un destinatario (nombres concatenados).
- Si el mismo teléfono trae `entry_code` distintos → `422`.
- Solo permitido si la campaña está en `draft`.
- Límites: `MAX_RECIPIENTS_PER_REQUEST` (default 500) y `MAX_RECIPIENTS_PER_CAMPAIGN` (default 2000).

**Respuesta `200`:** igual que `import-file`:

```json
{
  "campaign_id": "uuid",
  "total_rows": 2,
  "total_unique_recipients": 1,
  "total_invalid": 0,
  "status": "draft"
}
```

---

#### `POST /v1/campaigns/{campaign_id}/import-file` (deprecated)

Importa invitados desde CSV o TSV. **No envía mensajes.** Preferir `import-recipients`.

**Content-Type:** `multipart/form-data`

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `file` | archivo | — | CSV o TSV |
| `has_header` | bool | `true` | Primera fila es encabezado |
| `delimiter` | string | autodetect | `,` o `\t` |

**Columnas reconocidas**

- Nombre: `nombre completo`, `nombre`, `invitado`, `full name`, `name`
- Teléfono: `celular`, `telefono`, `teléfono`, `phone`, `mobile`

Si faltan columnas → `422`.

**Ejemplo CSV:**

```csv
Nombre Completo,Celular
"Juan Pérez","1157017999"
"María García","+5491157017999"
```

Los teléfonos argentinos se normalizan y agrupan (mismo número en distintos formatos = 1 destinatario).

**Respuesta `200`:**

```json
{
  "campaign_id": "uuid",
  "total_rows": 2,
  "total_unique_recipients": 1,
  "total_invalid": 0,
  "status": "draft"
}
```

> El archivo CSV **no se guarda** en disco. Solo se persisten las filas parseadas en Postgres.

---

#### `POST /v1/campaigns/{campaign_id}/dispatch`

Encola el envío de WhatsApp.

**Body (JSON):**

```json
{
  "delay_seconds": 2,
  "confirm": true
}
```

| Campo | Descripción |
|-------|-------------|
| `delay_seconds` | Pausa entre mensajes (≥ 0) |
| `confirm` | Debe ser `true` para ejecutar |

**Respuesta `200`:**

```json
{
  "job_id": "uuid",
  "status": "pending"
}
```

Errores comunes: `409` si la campaña ya está `processing`, `400` si no hay destinatarios o `confirm` es false.

---

#### `POST /v1/campaigns/{campaign_id}/retry-failed`

Reencola envío solo para destinatarios en estado `failed`.

**Respuesta:** igual que dispatch (`job_id`, `status`).

---

### Jobs

#### `GET /v1/jobs/{job_id}`

Estado de un job de la cola.

```json
{
  "id": "uuid",
  "campaign_id": "uuid",
  "job_type": "dispatch_campaign",
  "status": "done",
  "attempts": 1,
  "max_attempts": 5,
  "last_error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

Tipos: `dispatch_campaign`, `retry_failed`, `prepare_campaign`.

---

#### `GET /v1/campaigns/{campaign_id}/jobs`

Historial de jobs de una campaña.

---

### Destinatarios

#### `GET /v1/campaigns/{campaign_id}/recipients`

Lista paginada de destinatarios.

**Query params:**

| Param | Descripción |
|-------|-------------|
| `status` | `pending`, `processing`, `sent`, `failed`, `invalid`, `skipped` |
| `search` | Busca en nombre, teléfono o group_key |
| `page` | Default `1` |
| `page_size` | Default `50`, máx `200` |

**Ejemplo de item:**

```json
{
  "id": "uuid",
  "group_key": "541157017999",
  "button_phone": "1157017999",
  "display_name": "Juan, María",
  "entry_code": "ENT-A3B7K",
  "status": "sent",
  "attempt_count": 1,
  "last_error": null,
  "uploaded_qr_url": "https://.../qrs/{campaign_id}/{recipient_id}.jpg",
  "whatsapp_message_id": "wamid....",
  "whatsapp_message_status": "accepted"
}
```

---

### QR (público)

#### `GET /qrs/{campaign_id}/{recipient_id}.jpg`

Sirve la imagen JPG del QR. **Sin autenticación** (requerido por WhatsApp Cloud API).

El worker genera el QR, lo sube vía endpoint interno y guarda la URL en `uploaded_qr_url`.

---

### Interno (worker)

#### `POST /internal/v1/qrs`

Usado por el worker para guardar JPG en el volumen. Requiere `X-API-Key`.

**multipart/form-data:** `campaign_id`, `recipient_id`, `file`

No usar desde la webapp.

---

## Estados

### Campaña (`status`)

```text
draft → queued → processing → completed
                         └→ completed_with_errors
                         └→ failed
```

También existe `cancelled` (reservado).

### Destinatario (`status`)

`pending` → `processing` → `sent` | `failed` | `invalid` | `skipped`

### Job (`status`)

`pending` → `processing` → `done` | `failed`

---

## Códigos HTTP

| Código | Cuándo |
|--------|--------|
| `401` | API key inválida o ausente |
| `404` | Campaña/job no existe |
| `409` | Campaña no importable (no está en `draft`) o ya en proceso |
| `413` | Supera límite de invitados por request |
| `422` | Body inválido, conflicto de entry_code, CSV sin columnas válidas |
| `400` | Dispatch sin `confirm: true` o sin destinatarios |
| `503` | `/ready` con DB caída |

---

## Ejemplo completo (curl)

```bash
BASE=https://api-production-a4cb.up.railway.app
KEY=tu-api-key

# 1. Crear campaña
CAMPAIGN=$(curl -s -X POST "$BASE/v1/campaigns" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"organizer_name":"Tomás","event_at":"2026-12-12T21:00:00-03:00"}' \
  | jq -r .id)

# 2. Importar invitados (JSON)
curl -s -X POST "$BASE/v1/campaigns/$CAMPAIGN/import-recipients" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": [
      {"display_name": "Juan Pérez", "button_phone": "+5491155551234", "entry_code": "ENT-A3B7K"}
    ],
    "mode": "replace"
  }'

# 3. Despachar
curl -s -X POST "$BASE/v1/campaigns/$CAMPAIGN/dispatch" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"delay_seconds":2,"confirm":true}'

# 4. Consultar progreso
curl -s "$BASE/v1/campaigns/$CAMPAIGN/stats" -H "X-API-Key: $KEY"
```

---

## Almacenamiento de datos

| Dato | Dónde | Retención |
|------|-------|-----------|
| QR (JPG) | Volumen `/data/qrs` en Railway | Indefinida (sin auto-borrado) |
| Filas del CSV | Postgres (`campaign_import_rows`) | Hasta borrar campaña |
| Destinatarios / envíos | Postgres | Hasta borrar campaña |
| CSV original | No se guarda | — |

---

## Template WhatsApp

Por defecto: `confirmacion_registro` / `es_CL`.

Debe estar **APPROVED** en Meta Business Manager con:

- Header: imagen (URL del QR)
- Body: 5 variables (nombre, organizador, código entrada, fecha/hora, lugar)

Variables de entorno relevantes (solo servidor): `META_WHATSAPP_TOKEN`, `META_PHONE_NUMBER_ID`.

---

## Arquitectura (resumen)

```text
Webapp → API (FastAPI) → Postgres (cola + datos)
              ↑
Worker ─────────┘  (genera QR, sube a API, llama WhatsApp)
```

- **API:** recibe requests, no envía masivamente en la request HTTP.
- **Worker:** procesa jobs, respeta `delay_seconds`, registra cada intento.
- **Postgres:** campañas, destinatarios, jobs, auditoría de envíos.

---

## Desarrollo local

Ver [README.md](README.md). Base URL local: `http://localhost:8000`.

Variables mínimas en `.env`: `DATABASE_URL`, `INTERNAL_API_KEY`, `META_WHATSAPP_TOKEN`, `PUBLIC_BASE_URL`.
