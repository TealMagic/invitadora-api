import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.models import RecipientStatus
from app.db.repositories import RecipientRepository
from app.db.session import get_db
from app.integrations.storage import get_storage
from app.schemas import RecipientListResponse, RecipientResponse

router = APIRouter(prefix="/v1/campaigns", tags=["recipients"])
public_router = APIRouter(tags=["qrs"])


@router.get("/{campaign_id}/recipients", response_model=RecipientListResponse)
def list_recipients(
    campaign_id: uuid.UUID,
    status: RecipientStatus | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    repo = RecipientRepository(db)
    items, total = repo.list_by_campaign(
        campaign_id, status=status, search=search, page=page, page_size=page_size
    )
    return RecipientListResponse(
        items=[RecipientResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@public_router.get("/qrs/{campaign_id}/{recipient_id}.jpg")
def serve_qr(campaign_id: uuid.UUID, recipient_id: uuid.UUID):
    storage = get_storage()
    path = storage.get_qr_path(campaign_id, recipient_id)
    if not path:
        raise HTTPException(status_code=404, detail="QR not found")
    return FileResponse(path, media_type="image/jpeg")
