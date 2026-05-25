import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import (
    Campaign,
    CampaignImportRow,
    CampaignRecipient,
    CampaignStatus,
    Job,
    JobStatus,
    JobType,
    MessageAttempt,
    RecipientStatus,
    WhatsAppDeliveryStatus,
)
from app.domain.whatsapp_delivery import apply_status_update


class CampaignRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        organizer_name: str,
        event_at: datetime,
        template_name: str,
        template_language: str,
        created_by: str | None = None,
    ) -> Campaign:
        campaign = Campaign(
            organizer_name=organizer_name,
            event_at=event_at,
            template_name=template_name,
            template_language=template_language,
            created_by=created_by,
            status=CampaignStatus.draft,
        )
        self.db.add(campaign)
        self.db.commit()
        self.db.refresh(campaign)
        return campaign

    def get(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self.db.get(Campaign, campaign_id)

    def update_status(self, campaign: Campaign, status: CampaignStatus) -> Campaign:
        campaign.status = status
        self.db.commit()
        self.db.refresh(campaign)
        return campaign

    def update_fields(
        self,
        campaign: Campaign,
        *,
        organizer_name: str | None = None,
        event_at: datetime | None = None,
    ) -> Campaign:
        if organizer_name is not None:
            campaign.organizer_name = organizer_name
        if event_at is not None:
            campaign.event_at = event_at
        self.db.commit()
        self.db.refresh(campaign)
        return campaign

    def refresh_counters(self, campaign: Campaign) -> Campaign:
        recipients = (
            self.db.execute(
                select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id)
            )
            .scalars()
            .all()
        )
        campaign.total_unique_recipients = len(recipients)
        campaign.total_sent = sum(1 for r in recipients if r.status == RecipientStatus.sent)
        campaign.total_failed = sum(1 for r in recipients if r.status == RecipientStatus.failed)
        campaign.total_invalid = sum(1 for r in recipients if r.status == RecipientStatus.invalid)
        self.db.commit()
        self.db.refresh(campaign)
        return campaign


class ImportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_recipients(self, campaign_id: uuid.UUID) -> list[CampaignRecipient]:
        return (
            self.db.execute(
                select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)
            )
            .scalars()
            .all()
        )

    def max_import_line_no(self, campaign_id: uuid.UUID) -> int:
        rows = (
            self.db.execute(
                select(CampaignImportRow.line_no).where(CampaignImportRow.campaign_id == campaign_id)
            )
            .scalars()
            .all()
        )
        return max(rows, default=0)

    def replace_import_data(
        self,
        campaign: Campaign,
        import_rows: list[CampaignImportRow],
        recipients: list[CampaignRecipient],
        *,
        source_filename: str | None,
        source_content_type: str | None,
        total_rows: int,
    ) -> None:
        self.db.query(CampaignImportRow).filter(CampaignImportRow.campaign_id == campaign.id).delete()
        self.db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign.id).delete()
        self.db.add_all(import_rows)
        self.db.add_all(recipients)
        campaign.source_filename = source_filename
        campaign.source_content_type = source_content_type
        campaign.total_rows = total_rows
        campaign.total_unique_recipients = len(recipients)
        campaign.total_invalid = sum(1 for r in import_rows if r.normalization_error)
        self.db.commit()

    def append_import_data(
        self,
        campaign: Campaign,
        new_import_rows: list[CampaignImportRow],
        merged_recipients: list[CampaignRecipient],
        *,
        additional_rows: int,
    ) -> None:
        self.db.add_all(new_import_rows)
        for rec in merged_recipients:
            if rec.id is None:
                self.db.add(rec)
        campaign.total_rows += additional_rows
        campaign.total_unique_recipients = len(merged_recipients)
        all_rows = (
            self.db.execute(
                select(CampaignImportRow).where(CampaignImportRow.campaign_id == campaign.id)
            )
            .scalars()
            .all()
        )
        campaign.total_invalid = sum(1 for r in all_rows if r.normalization_error)
        self.db.commit()


class RecipientRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_whatsapp_message_id(self, message_id: str) -> CampaignRecipient | None:
        return (
            self.db.execute(
                select(CampaignRecipient).where(CampaignRecipient.whatsapp_message_id == message_id)
            )
            .scalar_one_or_none()
        )

    def get_by_wa_recipient_id(self, wa_recipient_id: str) -> CampaignRecipient | None:
        digits = wa_recipient_id.lstrip("+")
        return (
            self.db.execute(
                select(CampaignRecipient)
                .where(
                    (CampaignRecipient.to_e164_digits == digits)
                    | (CampaignRecipient.group_key == digits),
                )
                .order_by(CampaignRecipient.updated_at.desc())
                .limit(1)
            )
            .scalar_one_or_none()
        )

    def apply_whatsapp_status(
        self,
        recipient: CampaignRecipient,
        meta_status: str,
        timestamp: str | int | None = None,
        *,
        error_code: int | None = None,
        error_title: str | None = None,
    ) -> bool:
        changed = apply_status_update(
            recipient,
            meta_status,
            timestamp,
            error_code=error_code,
            error_title=error_title,
        )
        if changed:
            self.db.commit()
            self.db.refresh(recipient)
        return changed

    def list_by_campaign(
        self,
        campaign_id: uuid.UUID,
        *,
        status: RecipientStatus | None = None,
        whatsapp_delivery_status: WhatsAppDeliveryStatus | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CampaignRecipient], int]:
        q = select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)
        if status:
            q = q.where(CampaignRecipient.status == status)
        if whatsapp_delivery_status:
            q = q.where(CampaignRecipient.whatsapp_delivery_status == whatsapp_delivery_status)
        if search:
            like = f"%{search}%"
            q = q.where(
                (CampaignRecipient.display_name.ilike(like))
                | (CampaignRecipient.button_phone.ilike(like))
                | (CampaignRecipient.group_key.ilike(like))
            )
        total = len(self.db.execute(q).scalars().all())
        items = (
            self.db.execute(
                q.order_by(CampaignRecipient.created_at).offset((page - 1) * page_size).limit(page_size)
            )
            .scalars()
            .all()
        )
        return items, total

    def get_pending(self, campaign_id: uuid.UUID, limit: int = 100) -> list[CampaignRecipient]:
        return (
            self.db.execute(
                select(CampaignRecipient)
                .where(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.status == RecipientStatus.pending,
                )
                .order_by(CampaignRecipient.created_at)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def get_failed_retryable(self, campaign_id: uuid.UUID, limit: int = 100) -> list[CampaignRecipient]:
        return (
            self.db.execute(
                select(CampaignRecipient)
                .where(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.status == RecipientStatus.failed,
                )
                .order_by(CampaignRecipient.updated_at)
                .limit(limit)
            )
            .scalars()
            .all()
        )


class JobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        campaign_id: uuid.UUID,
        job_type: JobType,
        payload: dict | None = None,
    ) -> Job:
        job = Job(
            campaign_id=campaign_id,
            job_type=job_type,
            payload_json=payload or {},
            status=JobStatus.pending,
            available_at=datetime.now(timezone.utc),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get(self, job_id: uuid.UUID) -> Job | None:
        return self.db.get(Job, job_id)

    def list_by_campaign(self, campaign_id: uuid.UUID) -> list[Job]:
        return (
            self.db.execute(
                select(Job).where(Job.campaign_id == campaign_id).order_by(Job.created_at.desc())
            )
            .scalars()
            .all()
        )

    def claim_next(self, lock_token: str) -> Job | None:
        now = datetime.now(timezone.utc)
        job = (
            self.db.execute(
                select(Job)
                .where(
                    Job.status == JobStatus.pending,
                    Job.available_at <= now,
                )
                .order_by(Job.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            .scalar_one_or_none()
        )
        if not job:
            return None
        job.status = JobStatus.processing
        job.locked_at = now
        job.lock_token = lock_token
        job.attempts += 1
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_done(self, job: Job) -> None:
        job.status = JobStatus.done
        job.lock_token = None
        self.db.commit()

    def mark_failed(self, job: Job, error: str, retry: bool = False, delay_seconds: int = 30) -> None:
        job.last_error = error
        if retry and job.attempts < job.max_attempts:
            job.status = JobStatus.pending
            job.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            job.lock_token = None
        else:
            job.status = JobStatus.failed
            job.lock_token = None
        self.db.commit()


class MessageAttemptRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, attempt: MessageAttempt) -> MessageAttempt:
        self.db.add(attempt)
        self.db.commit()
        self.db.refresh(attempt)
        return attempt
