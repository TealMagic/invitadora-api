import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.security import require_api_key
from app.integrations.storage import get_storage
from app.schemas import QrUploadResponse

router = APIRouter(prefix="/internal/v1", tags=["internal"])


@router.post("/qrs", response_model=QrUploadResponse)
async def upload_qr(
    campaign_id: uuid.UUID = Form(...),
    recipient_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    _: str = Depends(require_api_key),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    storage = get_storage()
    public_url = storage.save_qr(campaign_id, recipient_id, content)
    return QrUploadResponse(public_url=public_url)
