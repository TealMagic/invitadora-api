import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.repositories import JobRepository
from app.db.session import get_db
from app.schemas import JobResponse

router = APIRouter(prefix="/v1", tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    job = JobRepository(db).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/campaigns/{campaign_id}/jobs", response_model=list[JobResponse])
def list_campaign_jobs(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    return JobRepository(db).list_by_campaign(campaign_id)
