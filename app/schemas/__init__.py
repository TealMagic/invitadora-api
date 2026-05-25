from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models import CampaignStatus, JobStatus, JobType, RecipientStatus
from app.domain.entry_codes import ENTRY_CODE_LENGTH, validate_entry_code


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


class RecipientInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=500)
    button_phone: str = Field(min_length=1, max_length=32)
    entry_code: str | None = Field(default=None, min_length=ENTRY_CODE_LENGTH, max_length=ENTRY_CODE_LENGTH)

    @field_validator("display_name", "button_phone", mode="before")
    @classmethod
    def strip_required(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("entry_code", mode="before")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("entry_code", mode="after")
    @classmethod
    def validate_entry_code_field(cls, value: str | None) -> str | None:
        return validate_entry_code(value)


class RecipientValidateInput(BaseModel):
    display_name: str = Field(default="", max_length=500)
    button_phone: str = Field(default="", max_length=32)
    entry_code: str | None = Field(default=None, min_length=ENTRY_CODE_LENGTH, max_length=ENTRY_CODE_LENGTH)

    @field_validator("display_name", "button_phone", mode="before")
    @classmethod
    def strip_fields(cls, value: str | None) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value)

    @field_validator("entry_code", mode="before")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("entry_code", mode="after")
    @classmethod
    def validate_entry_code_field(cls, value: str | None) -> str | None:
        return validate_entry_code(value)


class ImportRecipientsRequest(BaseModel):
    recipients: list[RecipientInput] = Field(min_length=1)
    mode: Literal["replace", "append"] = "replace"


class ValidateRecipientsRequest(BaseModel):
    recipients: list[RecipientValidateInput] = Field(min_length=1)
    mode: Literal["replace", "append"] = "replace"


class InvalidRecipientSample(BaseModel):
    display_name: str
    button_phone: str
    reason: str


class ValidateRecipientsResponse(BaseModel):
    total_rows: int
    total_unique_recipients: int
    total_invalid: int
    invalid_samples: list[InvalidRecipientSample]
    would_exceed_campaign_limit: bool
    can_import: bool
    can_dispatch: bool
    blocking_reasons: list[str] | None = None


class ImportSummary(BaseModel):
    total_rows: int
    total_unique_recipients: int
    total_invalid: int


class DispatchRequest(BaseModel):
    delay_seconds: float = Field(default=2.0, ge=0)
    confirm: bool = False
    recipients: list[RecipientInput] | None = None
    import_mode: Literal["replace", "append"] = "replace"


class DispatchResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    import_: ImportSummary | None = Field(default=None, alias="import")

    model_config = {"populate_by_name": True}


class CampaignUpdateRequest(BaseModel):
    organizer_name: str | None = Field(default=None, min_length=1, max_length=255)
    event_at: datetime | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "CampaignUpdateRequest":
        if self.organizer_name is None and self.event_at is None:
            raise ValueError("At least one field must be provided")
        return self


class CampaignReadinessResponse(BaseModel):
    campaign_id: UUID
    status: CampaignStatus
    total_unique_recipients: int
    ready_to_dispatch: bool
    blocking_reasons: list[str]


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
