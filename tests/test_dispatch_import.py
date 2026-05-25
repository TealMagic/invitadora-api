import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.db.models import Campaign, CampaignStatus, Job, JobStatus, JobType
from app.schemas import RecipientInput
from app.services.campaign_service import CampaignService


@pytest.fixture
def draft_campaign():
    campaign = Campaign(
        id=uuid.uuid4(),
        organizer_name="Test",
        event_at="2026-12-12T21:00:00+00:00",
        template_name="confirmacion_registro",
        template_language="es_CL",
        status=CampaignStatus.draft,
        total_unique_recipients=0,
    )
    return campaign


class TestDispatchWithRecipients:
    @patch.object(CampaignService, "import_guests")
    @patch.object(CampaignService, "preview_recipients")
    def test_dispatch_imports_then_queues(self, mock_preview, mock_import, draft_campaign):
        draft_campaign.total_unique_recipients = 1
        mock_preview.return_value = MagicMock(
            blocking_error=None,
            would_exceed_campaign_limit=False,
        )
        mock_import.return_value = draft_campaign

        job = Job(
            id=uuid.uuid4(),
            campaign_id=draft_campaign.id,
            job_type=JobType.dispatch_campaign,
            status=JobStatus.pending,
        )

        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)
        service.campaigns.update_status = MagicMock(return_value=draft_campaign)
        service.jobs.create = MagicMock(return_value=job)

        recipients = [
            RecipientInput(display_name="Juan", button_phone="+5491157017999"),
        ]
        result_job, _, summary = service.dispatch(
            draft_campaign.id,
            delay_seconds=2,
            confirm=True,
            recipients=recipients,
        )

        assert result_job == job
        assert summary is not None
        mock_import.assert_called_once()

    def test_dispatch_processing_raises(self, draft_campaign):
        draft_campaign.status = CampaignStatus.processing
        draft_campaign.total_unique_recipients = 5

        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)

        with pytest.raises(RuntimeError, match="already processing"):
            service.dispatch(draft_campaign.id, delay_seconds=2, confirm=True)

    def test_dispatch_queued_raises(self, draft_campaign):
        draft_campaign.status = CampaignStatus.queued
        draft_campaign.total_unique_recipients = 5

        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)

        with pytest.raises(RuntimeError, match="already queued"):
            service.dispatch(draft_campaign.id, delay_seconds=2, confirm=True)
