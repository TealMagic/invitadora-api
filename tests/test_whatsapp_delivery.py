import uuid
from datetime import datetime, timezone

from app.db.models import CampaignRecipient, WhatsAppDeliveryStatus
from app.domain.whatsapp_delivery import (
    apply_status_update,
    reset_whatsapp_delivery_fields,
)


def _recipient() -> CampaignRecipient:
    return CampaignRecipient(
        id=uuid.uuid4(),
        campaign_id=uuid.uuid4(),
        group_key="541157017999",
        to_e164_digits="541157017999",
        button_phone="1157017999",
        display_name="Test",
    )


class TestApplyStatusUpdate:
    def test_progression_sent_delivered_read(self):
        r = _recipient()
        assert apply_status_update(r, "sent", "1716652800") is True
        assert r.whatsapp_delivery_status == WhatsAppDeliveryStatus.sent
        assert r.whatsapp_sent_at is not None

        assert apply_status_update(r, "delivered", "1716652900") is True
        assert r.whatsapp_delivery_status == WhatsAppDeliveryStatus.delivered
        assert r.whatsapp_delivered_at is not None

        assert apply_status_update(r, "read", "1716653000") is True
        assert r.whatsapp_delivery_status == WhatsAppDeliveryStatus.read
        assert r.whatsapp_read_at is not None

    def test_does_not_regress_from_read(self):
        r = _recipient()
        apply_status_update(r, "read", "1716653000")
        assert apply_status_update(r, "delivered", "1716653100") is False
        assert r.whatsapp_delivery_status == WhatsAppDeliveryStatus.read

    def test_idempotent_same_status(self):
        r = _recipient()
        apply_status_update(r, "sent", "1716652800")
        sent_at = r.whatsapp_sent_at
        assert apply_status_update(r, "sent", "1716652801") is False
        assert r.whatsapp_sent_at == sent_at

    def test_failed_sets_error_fields(self):
        r = _recipient()
        apply_status_update(r, "sent", "1716652800")
        assert (
            apply_status_update(
                r,
                "failed",
                "1716652900",
                error_code=131047,
                error_title="Re-engagement message",
            )
            is True
        )
        assert r.whatsapp_delivery_status == WhatsAppDeliveryStatus.failed
        assert r.whatsapp_failed_at is not None
        assert r.whatsapp_error_code == 131047
        assert r.whatsapp_error_title == "Re-engagement message"

    def test_deleted_maps_to_failed(self):
        r = _recipient()
        assert apply_status_update(r, "deleted", "1716652800") is True
        assert r.whatsapp_delivery_status == WhatsAppDeliveryStatus.failed

    def test_reset_clears_all_whatsapp_fields(self):
        r = _recipient()
        r.whatsapp_message_id = "wamid.test"
        r.whatsapp_message_status = "accepted"
        apply_status_update(r, "read", "1716653000")
        reset_whatsapp_delivery_fields(r)
        assert r.whatsapp_message_id is None
        assert r.whatsapp_delivery_status is None
        assert r.whatsapp_read_at is None
