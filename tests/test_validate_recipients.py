import uuid
from unittest.mock import MagicMock

import pytest

from app.db.models import Campaign, CampaignStatus
from app.domain.guests import guests_from_validate_inputs
from app.schemas import RecipientValidateInput
from app.services.campaign_service import CampaignService


@pytest.fixture
def draft_campaign():
    return Campaign(
        id=uuid.uuid4(),
        organizer_name="Test",
        event_at="2026-12-12T21:00:00+00:00",
        template_name="confirmacion_registro",
        template_language="es_CL",
        status=CampaignStatus.draft,
    )


class TestPreviewRecipients:
    def test_empty_phone_invalid_sample(self, draft_campaign):
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)
        service.settings.max_recipients_per_request = 500
        service.settings.max_recipients_per_campaign = 2000

        items = [RecipientValidateInput(display_name="Ana", button_phone="")]
        guests = guests_from_validate_inputs(items)
        preview = service.preview_recipients(draft_campaign.id, guests)

        assert preview.total_invalid == 1
        assert preview.invalid_samples[0]["reason"] == "missing_phone"
        assert preview.can_import is True
        assert preview.can_dispatch is False

    def test_can_dispatch_false_when_processing(self, draft_campaign):
        draft_campaign.status = CampaignStatus.processing
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=draft_campaign)
        service.settings.max_recipients_per_request = 500
        service.settings.max_recipients_per_campaign = 2000

        items = [RecipientValidateInput(display_name="Juan", button_phone="+5491157017999")]
        guests = guests_from_validate_inputs(items)
        preview = service.preview_recipients(draft_campaign.id, guests)

        assert preview.can_import is False
        assert preview.can_dispatch is False

    def test_preview_from_validate_inputs_not_found(self):
        db = MagicMock()
        service = CampaignService(db)
        service.campaigns.get = MagicMock(return_value=None)

        with pytest.raises(LookupError):
            service.preview_from_validate_inputs(
                uuid.uuid4(),
                [RecipientValidateInput(display_name="A", button_phone="+5491157017999")],
            )
