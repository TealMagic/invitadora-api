import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
import requests
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_extra
from app.db.models import (
    CampaignStatus,
    ErrorStage,
    Job,
    JobType,
    MessageAttempt,
    RecipientStatus,
    WhatsAppDeliveryStatus,
)
from app.domain.whatsapp_delivery import reset_whatsapp_delivery_fields
from app.db.repositories import CampaignRepository, JobRepository, MessageAttemptRepository, RecipientRepository
from app.domain.entry_codes import generate_entry_code
from app.domain.payloads import build_payload_confirmacion
from app.domain.qrcode_service import generate_qr_image
from app.integrations.storage import get_storage
from app.integrations.whatsapp import extract_message_id, is_transient_error, send_message

logger = logging.getLogger(__name__)


class WorkerService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.jobs = JobRepository(db)
        self.campaigns = CampaignRepository(db)
        self.recipients = RecipientRepository(db)
        self.attempts = MessageAttemptRepository(db)
        self.storage = get_storage(self.settings)
        self.session = requests.Session()

    def process_job(self, job: Job) -> None:
        if not job.campaign_id:
            self.jobs.mark_failed(job, "Missing campaign_id")
            return

        campaign = self.campaigns.get(job.campaign_id)
        if not campaign:
            self.jobs.mark_failed(job, "Campaign not found")
            return

        self.campaigns.update_status(campaign, CampaignStatus.processing)
        delay = float(job.payload_json.get("delay_seconds", self.settings.default_send_delay_seconds))

        if job.job_type == JobType.dispatch_campaign:
            batch = self.recipients.get_pending(campaign.id, limit=self.settings.worker_batch_size)
        elif job.job_type == JobType.retry_failed:
            batch = self.recipients.get_failed_retryable(campaign.id, limit=self.settings.worker_batch_size)
            for r in batch:
                r.status = RecipientStatus.pending
                reset_whatsapp_delivery_fields(r)
            self.db.commit()
            batch = self.recipients.get_pending(campaign.id, limit=self.settings.worker_batch_size)
        else:
            self.jobs.mark_failed(job, f"Unsupported job type: {job.job_type}")
            return

        if not batch:
            self._finalize_campaign(campaign)
            self.jobs.mark_done(job)
            return

        for recipient in batch:
            self._process_recipient(campaign, recipient, delay)

        self.campaigns.refresh_counters(campaign)
        remaining_pending = self.recipients.get_pending(campaign.id, limit=1)
        remaining_failed = self.recipients.get_failed_retryable(campaign.id, limit=1)

        if remaining_pending or (job.job_type == JobType.retry_failed and remaining_failed):
            self.jobs.create(
                campaign_id=campaign.id,
                job_type=job.job_type,
                payload=job.payload_json,
            )
            self.jobs.mark_done(job)
        else:
            self._finalize_campaign(campaign)
            self.jobs.mark_done(job)

    def _finalize_campaign(self, campaign) -> None:
        self.campaigns.refresh_counters(campaign)
        if campaign.total_failed > 0:
            self.campaigns.update_status(campaign, CampaignStatus.completed_with_errors)
        else:
            self.campaigns.update_status(campaign, CampaignStatus.completed)

    def _process_recipient(self, campaign, recipient, delay: float) -> None:
        recipient.status = RecipientStatus.processing
        recipient.attempt_count += 1
        recipient.last_attempt_at = datetime.now(timezone.utc)
        self.db.commit()

        first_name = recipient.names_json[0] if recipient.names_json else ""
        if not recipient.entry_code:
            recipient.entry_code = generate_entry_code(recipient.button_phone, first_name)
        invitado_text = recipient.display_name
        fecha_hora_str = campaign.event_at.strftime("%d/%m/%Y %H:%M")

        try:
            qr_bytes = generate_qr_image(recipient.entry_code)
        except Exception as e:
            self._mark_failed(recipient, ErrorStage.qr, str(e))
            return

        try:
            image_url = self._upload_qr(campaign.id, recipient.id, qr_bytes)
        except Exception as e:
            self._mark_failed(recipient, ErrorStage.upload, str(e))
            return

        recipient.uploaded_qr_url = image_url
        payload = build_payload_confirmacion(
            to_e164_digits=recipient.to_e164_digits,
            invitado_text=invitado_text,
            organizador=campaign.organizer_name,
            referencia_entrada=recipient.entry_code,
            fecha_hora_str=fecha_hora_str,
            image_url=image_url,
            template_name=campaign.template_name,
            template_language=campaign.template_language,
        )

        ok, status, resp_text = send_message(
            self.session,
            self.settings.whatsapp_messages_url,
            self.settings.meta_whatsapp_token,
            payload,
        )

        attempt = MessageAttempt(
            campaign_id=campaign.id,
            recipient_id=recipient.id,
            attempt_no=recipient.attempt_count,
            request_payload_json=payload,
            response_status_code=status if status >= 0 else None,
            response_body_text=resp_text[:4000] if resp_text else None,
            success=ok,
            error_stage=None if ok else ErrorStage.whatsapp,
            error_message=None if ok else resp_text[:1000],
        )
        self.attempts.create(attempt)

        if ok:
            msg_id, msg_status = extract_message_id(resp_text)
            recipient.status = RecipientStatus.sent
            recipient.whatsapp_message_id = msg_id
            recipient.whatsapp_message_status = msg_status
            recipient.whatsapp_delivery_status = WhatsAppDeliveryStatus.pending_ack
            recipient.last_error = None
            log_extra(
                logger,
                logging.INFO,
                "message_sent",
                campaign_id=str(campaign.id),
                recipient_id=str(recipient.id),
            )
        else:
            recipient.status = RecipientStatus.failed
            recipient.last_error = resp_text[:1000]
            log_extra(
                logger,
                logging.ERROR,
                "message_failed",
                campaign_id=str(campaign.id),
                recipient_id=str(recipient.id),
                detail=f"status={status}",
            )

        self.db.commit()
        time.sleep(delay)

    def _upload_qr(self, campaign_id: uuid.UUID, recipient_id: uuid.UUID, qr_bytes: bytes) -> str:
        if self.settings.app_env == "development" and self.settings.api_internal_url.startswith("http://localhost"):
            return self.storage.save_qr(campaign_id, recipient_id, qr_bytes)

        url = f"{self.settings.api_internal_url.rstrip('/')}/internal/v1/qrs"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                headers={"X-API-Key": self.settings.internal_api_key},
                data={"campaign_id": str(campaign_id), "recipient_id": str(recipient_id)},
                files={"file": ("qr.jpg", qr_bytes, "image/jpeg")},
            )
            response.raise_for_status()
            return response.json()["public_url"]

    def _mark_failed(self, recipient, stage: ErrorStage, message: str) -> None:
        recipient.status = RecipientStatus.failed
        recipient.last_error = message
        attempt = MessageAttempt(
            campaign_id=recipient.campaign_id,
            recipient_id=recipient.id,
            attempt_no=recipient.attempt_count,
            request_payload_json={},
            success=False,
            error_stage=stage,
            error_message=message,
        )
        self.attempts.create(attempt)
        self.db.commit()
