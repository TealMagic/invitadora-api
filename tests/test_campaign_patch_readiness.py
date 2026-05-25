import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.db.models import Campaign, CampaignStatus
from app.services.campaign_service import CampaignService


@pytest.fixture
def draft_campaign():
    return Campaign(
        id=uuid.uuid4(),
        organizer_name="Test",
        event_at=datetime(2026, 12, 12, 21, 0, tzinfo=timezone.utc),
        template_name="confirmacion_registro",
        template_language="es_CL",
        status=CampaignStatus.draft,
        total_unique_recipients=10,
    )


class TestUpdateCampaign:
    def test_update_draft(self, draft_campaign):
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)
        service.campaigns.update_fields = MagicMock(return_value=draft_campaign)

        result = service.update_campaign(draft_campaign.id, organizer_name="Tomás")
        assert result.organizer_name == "Test"
        service.campaigns.update_fields.assert_called_once()

    def test_update_non_draft_raises(self, draft_campaign):
        draft_campaign.status = CampaignStatus.completed
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)

        with pytest.raises(RuntimeError, match="not editable"):
            service.update_campaign(draft_campaign.id, organizer_name="Tomás")


class TestReadiness:
    def test_ready_when_draft_with_recipients(self, draft_campaign):
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)

        readiness = service.get_readiness(draft_campaign.id)
        assert readiness["ready_to_dispatch"] is True
        assert readiness["blocking_reasons"] == []

    def test_not_ready_no_recipients(self, draft_campaign):
        draft_campaign.total_unique_recipients = 0
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)

        readiness = service.get_readiness(draft_campaign.id)
        assert readiness["ready_to_dispatch"] is False
        assert "no_recipients" in readiness["blocking_reasons"]

    def test_not_ready_processing(self, draft_campaign):
        draft_campaign.status = CampaignStatus.processing
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)

        readiness = service.get_readiness(draft_campaign.id)
        assert readiness["ready_to_dispatch"] is False
        assert "not_draft" in readiness["blocking_reasons"]
        assert "campaign_processing" in readiness["blocking_reasons"]
