import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    queued = "queued"
    processing = "processing"
    completed = "completed"
    completed_with_errors = "completed_with_errors"
    failed = "failed"
    cancelled = "cancelled"


class RecipientStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    sent = "sent"
    failed = "failed"
    invalid = "invalid"
    skipped = "skipped"


class JobType(str, enum.Enum):
    prepare_campaign = "prepare_campaign"
    dispatch_campaign = "dispatch_campaign"
    retry_failed = "retry_failed"


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class ErrorStage(str, enum.Enum):
    normalize = "normalize"
    qr = "qr"
    upload = "upload"
    whatsapp = "whatsapp"
    internal = "internal"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organizer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    template_name: Mapped[str] = mapped_column(String(128), nullable=False, default="confirmacion_registro")
    template_language: Mapped[str] = mapped_column(String(16), nullable=False, default="es_CL")
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status"), nullable=False, default=CampaignStatus.draft
    )
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    total_unique_recipients: Mapped[int] = mapped_column(Integer, default=0)
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_failed: Mapped[int] = mapped_column(Integer, default=0)
    total_invalid: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    import_rows: Mapped[list["CampaignImportRow"]] = relationship(back_populates="campaign")
    recipients: Mapped[list["CampaignRecipient"]] = relationship(back_populates="campaign")
    jobs: Mapped[list["Job"]] = relationship(back_populates="campaign")


class CampaignImportRow(Base):
    __tablename__ = "campaign_import_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_phone: Mapped[str] = mapped_column(Text, nullable=False, default="")
    normalized_group_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_to_digits: Mapped[str | None] = mapped_column(Text, nullable=True)
    button_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalization_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    was_grouped: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="import_rows")


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"
    __table_args__ = (Index("ix_campaign_recipients_campaign_status", "campaign_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    group_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    to_e164_digits: Mapped[str] = mapped_column(Text, nullable=False)
    button_phone: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False, default="Hola")
    names_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_lines_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    entry_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, name="recipient_status"), nullable=False, default=RecipientStatus.pending
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp_message_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_qr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="recipients")
    message_attempts: Mapped[list["MessageAttempt"]] = relationship(back_populates="recipient")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_available", "status", "available_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True
    )
    job_type: Mapped[JobType] = mapped_column(Enum(JobType, name="job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False, default=JobStatus.pending
    )
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped["Campaign | None"] = relationship(back_populates="jobs")


class MessageAttempt(Base):
    __tablename__ = "message_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaign_recipients.id", ondelete="CASCADE"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    request_payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_stage: Mapped[ErrorStage | None] = mapped_column(Enum(ErrorStage, name="error_stage"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    recipient: Mapped["CampaignRecipient"] = relationship(back_populates="message_attempts")
