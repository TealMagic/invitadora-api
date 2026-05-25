from datetime import datetime, timezone

from app.db.models import CampaignRecipient, WhatsAppDeliveryStatus

_PROGRESSION_RANK: dict[WhatsAppDeliveryStatus | None, int] = {
    None: 0,
    WhatsAppDeliveryStatus.pending_ack: 1,
    WhatsAppDeliveryStatus.sent: 2,
    WhatsAppDeliveryStatus.delivered: 3,
    WhatsAppDeliveryStatus.read: 4,
}

_META_STATUS_MAP: dict[str, WhatsAppDeliveryStatus] = {
    "sent": WhatsAppDeliveryStatus.sent,
    "delivered": WhatsAppDeliveryStatus.delivered,
    "read": WhatsAppDeliveryStatus.read,
    "failed": WhatsAppDeliveryStatus.failed,
    "deleted": WhatsAppDeliveryStatus.failed,
}


def meta_status_to_enum(meta_status: str) -> WhatsAppDeliveryStatus | None:
    return _META_STATUS_MAP.get(meta_status.lower())


def reset_whatsapp_delivery_fields(recipient: CampaignRecipient) -> None:
    recipient.whatsapp_message_id = None
    recipient.whatsapp_message_status = None
    recipient.whatsapp_delivery_status = None
    recipient.whatsapp_delivery_status_at = None
    recipient.whatsapp_sent_at = None
    recipient.whatsapp_delivered_at = None
    recipient.whatsapp_read_at = None
    recipient.whatsapp_failed_at = None
    recipient.whatsapp_error_code = None
    recipient.whatsapp_error_title = None


def _parse_meta_timestamp(timestamp: str | int | None) -> datetime:
    if timestamp is None:
        return datetime.now(timezone.utc)
    try:
        ts = int(timestamp)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _should_apply_progression(
    current: WhatsAppDeliveryStatus | None, incoming: WhatsAppDeliveryStatus
) -> bool:
    if incoming == WhatsAppDeliveryStatus.failed:
        return current != WhatsAppDeliveryStatus.read
    if current == WhatsAppDeliveryStatus.failed:
        return incoming != WhatsAppDeliveryStatus.failed
    current_rank = _PROGRESSION_RANK.get(current, 0)
    incoming_rank = _PROGRESSION_RANK.get(incoming, 0)
    return incoming_rank > current_rank


def _set_milestone_timestamp(
    recipient: CampaignRecipient, field: str, at: datetime
) -> None:
    if getattr(recipient, field) is None:
        setattr(recipient, field, at)


def apply_status_update(
    recipient: CampaignRecipient,
    meta_status: str,
    timestamp: str | int | None = None,
    *,
    error_code: int | None = None,
    error_title: str | None = None,
) -> bool:
    """
    Aplica una actualización de estado desde Meta. Retorna True si hubo cambio.
    """
    new_status = meta_status_to_enum(meta_status)
    if new_status is None:
        return False

    at = _parse_meta_timestamp(timestamp)
    current = recipient.whatsapp_delivery_status

    if not _should_apply_progression(current, new_status):
        return False

    recipient.whatsapp_delivery_status = new_status
    recipient.whatsapp_delivery_status_at = at

    if new_status == WhatsAppDeliveryStatus.sent:
        _set_milestone_timestamp(recipient, "whatsapp_sent_at", at)
    elif new_status == WhatsAppDeliveryStatus.delivered:
        _set_milestone_timestamp(recipient, "whatsapp_delivered_at", at)
        if recipient.whatsapp_sent_at is None:
            _set_milestone_timestamp(recipient, "whatsapp_sent_at", at)
    elif new_status == WhatsAppDeliveryStatus.read:
        _set_milestone_timestamp(recipient, "whatsapp_read_at", at)
        if recipient.whatsapp_delivered_at is None:
            _set_milestone_timestamp(recipient, "whatsapp_delivered_at", at)
        if recipient.whatsapp_sent_at is None:
            _set_milestone_timestamp(recipient, "whatsapp_sent_at", at)
    elif new_status == WhatsAppDeliveryStatus.failed:
        _set_milestone_timestamp(recipient, "whatsapp_failed_at", at)
        if error_code is not None:
            recipient.whatsapp_error_code = error_code
        if error_title is not None:
            recipient.whatsapp_error_title = error_title

    return True
