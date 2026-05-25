import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.session import get_db
from app.domain.guests import guests_from_recipient_inputs
from app.schemas import ImportRecipientsRequest, ImportResultResponse
from app.services.campaign_service import CampaignService

router = APIRouter(prefix="/v1/campaigns", tags=["imports"])


def _import_result(campaign) -> ImportResultResponse:
    return ImportResultResponse(
        campaign_id=campaign.id,
        total_rows=campaign.total_rows,
        total_unique_recipients=campaign.total_unique_recipients,
        total_invalid=campaign.total_invalid,
        status=campaign.status,
    )


def _handle_import_errors(fn):
    try:
        return fn()
    except LookupError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        detail = str(e)
        status_code = 413 if detail.startswith("Too many recipients") else 422
        raise HTTPException(status_code=status_code, detail=detail)


@router.post(
    "/{campaign_id}/import-recipients",
    response_model=ImportResultResponse,
    summary="Import recipients from JSON",
)
def import_recipients(
    campaign_id: uuid.UUID,
    payload: ImportRecipientsRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    service = CampaignService(db)
    guests = guests_from_recipient_inputs(payload.recipients)

    def _run():
        return service.import_guests(campaign_id, guests, source="json")

    campaign = _handle_import_errors(_run)
    return _import_result(campaign)


@router.post(
    "/{campaign_id}/import-file",
    response_model=ImportResultResponse,
    deprecated=True,
    summary="Import recipients from CSV (deprecated)",
)
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

    def _run():
        return service.import_file(
            campaign_id,
            content,
            filename=file.filename,
            content_type=file.content_type,
            delimiter=delimiter,
            has_header=has_header,
        )

    campaign = _handle_import_errors(_run)
    return _import_result(campaign)
