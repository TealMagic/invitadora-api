from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import CampaignStatus, JobStatus, JobType, RecipientStatus


class CampaignCreateRequest(BaseModel):
    organizer_name: str
    event_at: datetime
    template_name: str = "confirmacion_registro"
    template_language: str = "es_CL"
    created_by: str | None = None


class CampaignResponse(BaseModel):
    id: UUID
    status: CampaignStatus
    organizer_name: str
    event_at: datetime
    template_name: str
    template_language: str
    source_filename: str | None = None
    total_rows: int = 0
    total_unique_recipients: int = 0
    total_sent: int = 0
    total_failed: int = 0
    total_invalid: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignStatsResponse(BaseModel):
    campaign_id: UUID
    status: CampaignStatus
    total_rows: int
    total_unique_recipients: int
    total_sent: int
    total_failed: int
    total_invalid: int
    pending: int = 0
    processing: int = 0


class ImportResultResponse(BaseModel):
    campaign_id: UUID
    total_rows: int
    total_unique_recipients: int
    total_invalid: int
    status: CampaignStatus


class DispatchRequest(BaseModel):
    delay_seconds: float = Field(default=2.0, ge=0)
    confirm: bool = False


class DispatchResponse(BaseModel):
    job_id: UUID
    status: JobStatus


class JobResponse(BaseModel):
    id: UUID
    campaign_id: UUID | None
    job_type: JobType
    status: JobStatus
    attempts: int
    max_attempts: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecipientResponse(BaseModel):
    id: UUID
    group_key: str
    button_phone: str
    display_name: str
    entry_code: str | None
    status: RecipientStatus
    attempt_count: int
    last_error: str | None
    uploaded_qr_url: str | None
    whatsapp_message_id: str | None
    whatsapp_message_status: str | None

    model_config = {"from_attributes": True}


class RecipientListResponse(BaseModel):
    items: list[RecipientResponse]
    total: int
    page: int
    page_size: int


class QrUploadResponse(BaseModel):
    public_url: str
