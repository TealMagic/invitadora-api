# Invitadora API

API para campañas de invitaciones WhatsApp con procesamiento asíncrono vía worker.

## Stack

- Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Postgres
- Railway: servicios `api`, `worker`, `postgres`
- QR almacenados en volumen persistente (`/data/qrs`) servidos por la API

## Desarrollo local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
python -m worker.run_worker
pytest
```

## Endpoints principales

- `GET /health`
- `POST /v1/campaigns` (header `X-API-Key`)
- `POST /v1/campaigns/{id}/import-file`
- `POST /v1/campaigns/{id}/dispatch`
- `GET /v1/campaigns/{id}/stats`
- `GET /qrs/{campaign_id}/{recipient_id}.jpg` (público, para WhatsApp)

## Railway

**Requisito:** plan Railway activo (Hobby o superior). Si el trial expiró, renová en [railway.com/pricing](https://railway.com/pricing).

### Setup vía MCP o dashboard

1. Crear proyecto `invitadora-api`
2. Conectar repo GitHub (push de este código)
3. Servicios:
   - **api**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **worker**: `python -m worker.run_worker`
   - **postgres**: plugin Railway
4. Volumen en **api** montado en `/data/qrs` (Railway no permite volumen compartido; el worker sube QR vía `POST /internal/v1/qrs`)
5. Variables compartidas (ver `.env.example`); `DATABASE_URL` la inyecta Postgres
6. Generar dominio público → setear `PUBLIC_BASE_URL` y `API_INTERNAL_URL`
7. Tras primer deploy: `python -m scripts.migrate` (one-off o release command)
8. Verificar `GET /health`

## Template WhatsApp

Verificar en Business Manager que `confirmacion_registro` esté APPROVED con header IMAGE y 5 variables body.
