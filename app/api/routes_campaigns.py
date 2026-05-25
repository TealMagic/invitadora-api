import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.session import get_db
from app.schemas import (
    CampaignCreateRequest,
    CampaignReadinessResponse,
    CampaignResponse,
    CampaignStatsResponse,
    CampaignUpdateRequest,
    DispatchRequest,
    DispatchResponse,
    ImportSummary,
)
from app.services.campaign_service import CampaignService

router = APIRouter(prefix="/v1/campaigns", tags=["campaigns"])


def _dispatch_error_status(detail: str) -> int:
    if detail.startswith("Too many recipients"):
        return 413
    return 422


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreateRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    service = CampaignService(db)
    campaign = service.create_campaign(
        organizer_name=payload.organizer_name,
        event_at=payload.event_at,
        template_name=payload.template_name,
        template_language=payload.template_language,
        created_by=payload.created_by,
    )
    return campaign


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    service = CampaignService(db)
    campaign = service.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.patch("/{campaign_id}", response_model=CampaignResponse)
def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignUpdateRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    service = CampaignService(db)
    try:
        campaign = service.update_campaign(
            campaign_id,
            organizer_name=payload.organizer_name,
            event_at=payload.event_at,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return campaign


@router.get("/{campaign_id}/stats", response_model=CampaignStatsResponse)
def get_campaign_stats(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    service = CampaignService(db)
    stats = service.get_stats(campaign_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return stats


@router.get("/{campaign_id}/readiness", response_model=CampaignReadinessResponse)
def get_campaign_readiness(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    service = CampaignService(db)
    readiness = service.get_readiness(campaign_id)
    if not readiness:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return readiness


@router.post("/{campaign_id}/dispatch", response_model=DispatchResponse)
def dispatch_campaign(
    campaign_id: uuid.UUID,
    payload: DispatchRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    service = CampaignService(db)
    try:
        job, _, import_summary = service.dispatch(
            campaign_id,
            delay_seconds=payload.delay_seconds,
            confirm=payload.confirm,
            recipients=payload.recipients,
            import_mode=payload.import_mode,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        detail = str(e)
        code = 400 if detail == "confirm must be true" or detail == "No recipients to dispatch" else _dispatch_error_status(detail)
        raise HTTPException(status_code=code, detail=detail)

    import_block = None
    if import_summary:
        import_block = ImportSummary(**import_summary)

    return DispatchResponse(job_id=job.id, status=job.status, import_=import_block)


@router.post("/{campaign_id}/retry-failed", response_model=DispatchResponse)
def retry_failed(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    service = CampaignService(db)
    try:
        job, _ = service.retry_failed(campaign_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return DispatchResponse(job_id=job.id, status=job.status)
