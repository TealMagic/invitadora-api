import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_extra
from app.db.repositories import RecipientRepository
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


def _verify_signature(app_secret: str, body: bytes, signature_header: str | None) -> bool:
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header[7:], expected)


def _extract_status_updates(payload: dict) -> list[dict]:
    updates: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status in value.get("statuses", []):
                updates.append(status)
    return updates


@router.get("/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_webhook_verify_token:
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if settings.meta_app_secret and not _verify_signature(
        settings.meta_app_secret, body, signature
    ):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as err:
        raise HTTPException(status_code=400, detail="Invalid JSON") from err

    repo = RecipientRepository(db)
    processed = 0

    for status_update in _extract_status_updates(payload):
        wamid = status_update.get("id")
        meta_status = status_update.get("status")
        if not wamid or not meta_status:
            continue

        recipient = repo.get_by_whatsapp_message_id(wamid)
        if not recipient:
            wa_id = status_update.get("recipient_id")
            if wa_id:
                recipient = repo.get_by_wa_recipient_id(str(wa_id))

        if not recipient:
            log_extra(
                logger,
                logging.WARNING,
                "webhook_recipient_not_found",
                detail=f"wamid={wamid} status={meta_status}",
            )
            continue

        errors = status_update.get("errors") or []
        error_code = None
        error_title = None
        if errors:
            first = errors[0]
            error_code = first.get("code")
            error_title = first.get("title") or first.get("message")

        if repo.apply_whatsapp_status(
            recipient,
            meta_status,
            status_update.get("timestamp"),
            error_code=error_code,
            error_title=error_title,
        ):
            processed += 1
            log_extra(
                logger,
                logging.INFO,
                "webhook_status_applied",
                recipient_id=str(recipient.id),
                detail=f"wamid={wamid} status={meta_status}",
            )

    return {"ok": True, "processed": processed}
