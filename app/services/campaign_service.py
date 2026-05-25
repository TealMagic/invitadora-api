import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Campaign,
    CampaignStatus,
    JobType,
    RecipientStatus,
)
from app.db.repositories import CampaignRepository, ImportRepository, JobRepository
from app.domain.guests import EntryCodeConflictError, GuestRow, ImportColumnError, read_guests_from_bytes
from app.services.import_service import build_import_entities


class CampaignService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.campaigns = CampaignRepository(db)
        self.imports = ImportRepository(db)
        self.jobs = JobRepository(db)

    def create_campaign(
        self,
        *,
        organizer_name: str,
        event_at: datetime,
        template_name: str,
        template_language: str,
        created_by: str | None = None,
    ) -> Campaign:
        return self.campaigns.create(
            organizer_name=organizer_name,
            event_at=event_at,
            template_name=template_name,
            template_language=template_language,
            created_by=created_by,
        )

    def get_campaign(self, campaign_id: uuid.UUID) -> Campaign | None:
        return self.campaigns.get(campaign_id)

    def get_stats(self, campaign_id: uuid.UUID) -> dict | None:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            return None
        recipients = campaign.recipients
        return {
            "campaign_id": campaign.id,
            "status": campaign.status,
            "total_rows": campaign.total_rows,
            "total_unique_recipients": campaign.total_unique_recipients,
            "total_sent": campaign.total_sent,
            "total_failed": campaign.total_failed,
            "total_invalid": campaign.total_invalid,
            "pending": sum(1 for r in recipients if r.status == RecipientStatus.pending),
            "processing": sum(1 for r in recipients if r.status == RecipientStatus.processing),
        }

    def _ensure_importable(self, campaign: Campaign) -> None:
        if campaign.status != CampaignStatus.draft:
            raise RuntimeError(f"Campaign not importable in status {campaign.status.value}")

    def import_guests(
        self,
        campaign_id: uuid.UUID,
        guests: list[GuestRow],
        *,
        source: Literal["csv", "json"],
        source_filename: str | None = None,
        source_content_type: str | None = None,
    ) -> Campaign:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            raise LookupError("Campaign not found")
        self._ensure_importable(campaign)

        if len(guests) > self.settings.max_recipients_per_request:
            raise ValueError(
                f"Too many recipients in request (max {self.settings.max_recipients_per_request})"
            )

        try:
            import_rows, recipients = build_import_entities(campaign.id, guests)
        except EntryCodeConflictError as e:
            raise ValueError(str(e)) from e

        if len(recipients) > self.settings.max_recipients_per_campaign:
            raise ValueError(
                f"Campaign recipient limit exceeded (max {self.settings.max_recipients_per_campaign})"
            )

        label = source_filename
        if source == "json" and not label:
            label = "import-recipients.json"
        content_type = source_content_type
        if source == "json" and not content_type:
            content_type = "application/json"

        self.imports.replace_import_data(
            campaign,
            import_rows,
            recipients,
            source_filename=label,
            source_content_type=content_type,
            total_rows=len(guests),
        )
        self.db.refresh(campaign)
        return campaign

    def import_file(
        self,
        campaign_id: uuid.UUID,
        content: bytes,
        *,
        filename: str | None,
        content_type: str | None,
        delimiter: str | None,
        has_header: bool,
    ) -> Campaign:
        try:
            guests = read_guests_from_bytes(content, delimiter=delimiter, has_header=has_header)
        except ImportColumnError as e:
            raise ValueError(str(e)) from e

        return self.import_guests(
            campaign_id,
            guests,
            source="csv",
            source_filename=filename,
            source_content_type=content_type,
        )

    def dispatch(self, campaign_id: uuid.UUID, *, delay_seconds: float, confirm: bool) -> tuple:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            raise LookupError("Campaign not found")
        if campaign.status == CampaignStatus.processing:
            raise RuntimeError("Campaign already processing")
        if not confirm:
            raise ValueError("confirm must be true")
        if campaign.total_unique_recipients == 0:
            raise ValueError("No recipients to dispatch")

        job = self.jobs.create(
            campaign_id=campaign.id,
            job_type=JobType.dispatch_campaign,
            payload={"delay_seconds": delay_seconds},
        )
        self.campaigns.update_status(campaign, CampaignStatus.queued)
        return job, campaign

    def retry_failed(self, campaign_id: uuid.UUID) -> tuple:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            raise LookupError("Campaign not found")
        if campaign.status == CampaignStatus.processing:
            raise RuntimeError("Campaign already processing")

        job = self.jobs.create(
            campaign_id=campaign.id,
            job_type=JobType.retry_failed,
            payload={"delay_seconds": 2.0},
        )
        self.campaigns.update_status(campaign, CampaignStatus.queued)
        return job, campaign
