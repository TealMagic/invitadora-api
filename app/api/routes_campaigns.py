import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.session import get_db
from app.schemas import (
    CampaignCreateRequest,
    CampaignResponse,
    CampaignStatsResponse,
    DispatchRequest,
    DispatchResponse,
)
from app.services.campaign_service import CampaignService

router = APIRouter(prefix="/v1/campaigns", tags=["campaigns"])


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


@router.post("/{campaign_id}/dispatch", response_model=DispatchResponse)
def dispatch_campaign(
    campaign_id: uuid.UUID,
    payload: DispatchRequest,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    service = CampaignService(db)
    try:
        job, _ = service.dispatch(campaign_id, delay_seconds=payload.delay_seconds, confirm=payload.confirm)
    except LookupError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return DispatchResponse(job_id=job.id, status=job.status)


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
