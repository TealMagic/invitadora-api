import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.db.models import Campaign, CampaignStatus
from app.domain.guests import GuestRow
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
    )
    return campaign


class TestImportGuestsLimits:
    def test_rejects_when_exceeds_per_request_limit(self, draft_campaign):
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)
        service.settings.max_recipients_per_request = 2
        service.settings.max_recipients_per_campaign = 2000

        guests = [
            GuestRow(1, "A", "+5491157017999"),
            GuestRow(2, "B", "+5491157017998"),
            GuestRow(3, "C", "+5491157017997"),
        ]

        with pytest.raises(ValueError, match="Too many recipients in request"):
            service.import_guests(draft_campaign.id, guests, source="json")

    def test_rejects_when_exceeds_per_campaign_limit(self, draft_campaign):
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)
        service.settings.max_recipients_per_request = 500
        service.settings.max_recipients_per_campaign = 1

        guests = [
            GuestRow(1, "A", "+5491157017999"),
            GuestRow(2, "B", "+5491157017998"),
        ]

        with pytest.raises(ValueError, match="Campaign recipient limit exceeded"):
            service.import_guests(draft_campaign.id, guests, source="json")

    def test_rejects_non_draft_campaign(self, draft_campaign):
        draft_campaign.status = CampaignStatus.queued
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)

        with pytest.raises(RuntimeError, match="not importable"):
            service.import_guests(
                draft_campaign.id,
                [GuestRow(1, "A", "+5491157017999")],
                source="json",
            )

    @patch("app.services.campaign_service.build_import_entities")
    def test_import_guests_success(self, mock_build, draft_campaign):
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)
        service.settings.max_recipients_per_request = 500
        service.settings.max_recipients_per_campaign = 2000
        service.imports.replace_import_data = MagicMock()
        mock_build.return_value = ([], [])

        result = service.import_guests(
            draft_campaign.id,
            [GuestRow(1, "A", "+5491157017999")],
            source="json",
        )

        assert result is draft_campaign
        service.imports.replace_import_data.assert_called_once()
