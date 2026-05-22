import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.models import CampaignStatus
from app.db.session import get_db
from app.schemas import ImportResultResponse
from app.services.campaign_service import CampaignService

router = APIRouter(prefix="/v1/campaigns", tags=["imports"])


@router.post("/{campaign_id}/import-file", response_model=ImportResultResponse)
async def import_file(
    campaign_id: uuid.UUID,
    file: UploadFile = File(...),
    delimiter: str | None = Form(default=None),
    has_header: bool = Form(default=True),
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    content = await file.read()
    service = CampaignService(db)
    try:
        campaign = service.import_file(
            campaign_id,
            content,
            filename=file.filename,
            content_type=file.content_type,
            delimiter=delimiter,
            has_header=has_header,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return ImportResultResponse(
        campaign_id=campaign.id,
        total_rows=campaign.total_rows,
        total_unique_recipients=campaign.total_unique_recipients,
        total_invalid=campaign.total_invalid,
        status=campaign.status,
    )
