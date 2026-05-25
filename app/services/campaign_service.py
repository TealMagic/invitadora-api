import uuid
from dataclasses import dataclass
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
from app.domain.guests import (
    EntryCodeConflictError,
    GuestRow,
    guests_from_recipient_inputs,
    guests_from_validate_inputs,
    invalid_sample_from_guest,
    normalization_error_to_reason,
    prepare_recipients,
)
from app.services.import_service import build_import_entities, merge_prepared_into_recipients

INVALID_SAMPLES_LIMIT = 10


@dataclass
class RecipientsPreview:
    total_rows: int
    total_unique_recipients: int
    total_invalid: int
    invalid_samples: list[dict]
    would_exceed_campaign_limit: bool
    can_import: bool
    can_dispatch: bool
    blocking_error: str | None = None


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

    def _ensure_editable(self, campaign: Campaign) -> None:
        if campaign.status != CampaignStatus.draft:
            raise RuntimeError(f"Campaign not editable in status {campaign.status.value}")

    def _offset_guest_line_numbers(self, guests: list[GuestRow], offset: int) -> list[GuestRow]:
        return [
            GuestRow(
                line_no=g.line_no + offset,
                name=g.name,
                raw_phone=g.raw_phone,
                entry_code=g.entry_code,
            )
            for g in guests
        ]

    def _check_request_limit(self, guests: list[GuestRow]) -> None:
        if len(guests) > self.settings.max_recipients_per_request:
            raise ValueError(
                f"Too many recipients in request (max {self.settings.max_recipients_per_request})"
            )

    def preview_recipients(
        self,
        campaign_id: uuid.UUID,
        guests: list[GuestRow],
        *,
        mode: Literal["replace", "append"] = "replace",
    ) -> RecipientsPreview:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            raise LookupError("Campaign not found")

        self._check_request_limit(guests)
        total_rows = len(guests)

        recipients_prepared, invalid = prepare_recipients(guests)
        total_invalid = len(invalid)

        invalid_samples = [
            invalid_sample_from_guest(
                g,
                normalization_error_to_reason(err),
            )
            for g, err in invalid[:INVALID_SAMPLES_LIMIT]
        ]

        blocking_error: str | None = None
        try:
            build_import_entities(campaign_id, guests)
        except EntryCodeConflictError as e:
            blocking_error = str(e)

        if mode == "append":
            existing = self.imports.list_recipients(campaign_id)
            try:
                merged = merge_prepared_into_recipients(existing, recipients_prepared, campaign_id)
            except ValueError as e:
                blocking_error = str(e)
                projected_unique = len(existing)
            else:
                projected_unique = len(merged)
        else:
            projected_unique = len(recipients_prepared)

        would_exceed = projected_unique > self.settings.max_recipients_per_campaign
        can_import = (
            campaign.status == CampaignStatus.draft
            and not would_exceed
            and blocking_error is None
        )
        can_dispatch = (
            can_import
            and projected_unique > 0
            and campaign.status not in (CampaignStatus.processing, CampaignStatus.queued)
        )

        return RecipientsPreview(
            total_rows=total_rows,
            total_unique_recipients=projected_unique,
            total_invalid=total_invalid,
            invalid_samples=invalid_samples,
            would_exceed_campaign_limit=would_exceed,
            can_import=can_import,
            can_dispatch=can_dispatch,
            blocking_error=blocking_error,
        )

    def _assert_preview_importable(self, preview: RecipientsPreview) -> None:
        if preview.blocking_error:
            raise ValueError(preview.blocking_error)
        if preview.would_exceed_campaign_limit:
            raise ValueError(
                f"Campaign recipient limit exceeded (max {self.settings.max_recipients_per_campaign})"
            )

    def import_guests(
        self,
        campaign_id: uuid.UUID,
        guests: list[GuestRow],
        *,
        source: Literal["csv", "json"],
        source_filename: str | None = None,
        source_content_type: str | None = None,
        mode: Literal["replace", "append"] = "replace",
    ) -> Campaign:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            raise LookupError("Campaign not found")
        self._ensure_importable(campaign)
        self._check_request_limit(guests)

        try:
            if mode == "append":
                return self._import_guests_append(
                    campaign,
                    guests,
                    source=source,
                    source_filename=source_filename,
                    source_content_type=source_content_type,
                )
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

    def _import_guests_append(
        self,
        campaign: Campaign,
        guests: list[GuestRow],
        *,
        source: Literal["csv", "json"],
        source_filename: str | None,
        source_content_type: str | None,
    ) -> Campaign:
        offset = self.imports.max_import_line_no(campaign.id)
        offset_guests = self._offset_guest_line_numbers(guests, offset)

        try:
            import_rows, _ = build_import_entities(campaign.id, offset_guests)
            recipients_prepared, _ = prepare_recipients(offset_guests)
            existing = self.imports.list_recipients(campaign.id)
            merged = merge_prepared_into_recipients(existing, recipients_prepared, campaign.id)
        except EntryCodeConflictError as e:
            raise ValueError(str(e)) from e

        if len(merged) > self.settings.max_recipients_per_campaign:
            raise ValueError(
                f"Campaign recipient limit exceeded (max {self.settings.max_recipients_per_campaign})"
            )

        self.imports.append_import_data(
            campaign,
            import_rows,
            merged,
            additional_rows=len(guests),
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
        mode: Literal["replace", "append"] = "replace",
    ) -> Campaign:
        from app.domain.guests import ImportColumnError, read_guests_from_bytes

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
            mode=mode,
        )

    def _ensure_dispatchable(self, campaign: Campaign) -> None:
        if campaign.status == CampaignStatus.processing:
            raise RuntimeError("Campaign already processing")
        if campaign.status == CampaignStatus.queued:
            raise RuntimeError("Campaign already queued for dispatch")

    def dispatch(
        self,
        campaign_id: uuid.UUID,
        *,
        delay_seconds: float,
        confirm: bool,
        recipients: list | None = None,
        import_mode: Literal["replace", "append"] = "replace",
    ) -> tuple:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            raise LookupError("Campaign not found")

        import_summary: dict | None = None

        if recipients is not None:
            self._ensure_importable(campaign)
            guests = guests_from_recipient_inputs(recipients)
            preview = self.preview_recipients(campaign_id, guests, mode=import_mode)
            self._assert_preview_importable(preview)
            campaign = self.import_guests(
                campaign_id,
                guests,
                source="json",
                mode=import_mode,
            )
            import_summary = {
                "total_rows": campaign.total_rows,
                "total_unique_recipients": campaign.total_unique_recipients,
                "total_invalid": campaign.total_invalid,
            }

        self._ensure_dispatchable(campaign)
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
        return job, campaign, import_summary

    def retry_failed(self, campaign_id: uuid.UUID) -> tuple:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            raise LookupError("Campaign not found")
        self._ensure_dispatchable(campaign)

        job = self.jobs.create(
            campaign_id=campaign.id,
            job_type=JobType.retry_failed,
            payload={"delay_seconds": 2.0},
        )
        self.campaigns.update_status(campaign, CampaignStatus.queued)
        return job, campaign

    def update_campaign(
        self,
        campaign_id: uuid.UUID,
        *,
        organizer_name: str | None = None,
        event_at: datetime | None = None,
    ) -> Campaign:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            raise LookupError("Campaign not found")
        self._ensure_editable(campaign)
        return self.campaigns.update_fields(
            campaign,
            organizer_name=organizer_name,
            event_at=event_at,
        )

    def get_readiness(self, campaign_id: uuid.UUID) -> dict | None:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            return None

        blocking: list[str] = []
        if campaign.status != CampaignStatus.draft:
            blocking.append("not_draft")
        if campaign.status == CampaignStatus.processing:
            blocking.append("campaign_processing")
        if campaign.status == CampaignStatus.queued:
            blocking.append("campaign_queued")
        if campaign.total_unique_recipients == 0:
            blocking.append("no_recipients")

        return {
            "campaign_id": campaign.id,
            "status": campaign.status,
            "total_unique_recipients": campaign.total_unique_recipients,
            "ready_to_dispatch": len(blocking) == 0,
            "blocking_reasons": blocking,
        }

    def preview_from_validate_inputs(
        self,
        campaign_id: uuid.UUID,
        items: list,
        *,
        mode: Literal["replace", "append"] = "replace",
    ) -> RecipientsPreview:
        guests = guests_from_validate_inputs(items)
        return self.preview_recipients(campaign_id, guests, mode=mode)
