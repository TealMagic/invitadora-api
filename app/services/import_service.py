import uuid
from collections import defaultdict

from app.db.models import CampaignImportRow, CampaignRecipient, RecipientStatus
from app.domain.guests import GuestRow, PreparedRecipient, prepare_recipients
from app.domain.phones import normalize_ar_phone


def build_import_entities(
    campaign_id: uuid.UUID,
    guests: list[GuestRow],
) -> tuple[list[CampaignImportRow], list[CampaignRecipient]]:
    recipients, invalid_rows = prepare_recipients(guests)
    grouped_lines: dict[str, list[int]] = defaultdict(list)
    for rec in recipients:
        for line in rec.source_lines:
            grouped_lines[rec.group_key].append(line)

    import_rows: list[CampaignImportRow] = []
    for g in guests:
        group_key, to_digits, btn, err = normalize_ar_phone(g.raw_phone)
        was_grouped = False
        if group_key and group_key in grouped_lines and len(grouped_lines[group_key]) > 1:
            was_grouped = True
        import_rows.append(
            CampaignImportRow(
                campaign_id=campaign_id,
                line_no=g.line_no,
                raw_name=g.name,
                raw_phone=g.raw_phone,
                normalized_group_key=group_key,
                normalized_to_digits=to_digits,
                button_phone=btn,
                normalization_error=err,
                was_grouped=was_grouped,
            )
        )

    db_recipients = [_recipient_from_prepared(campaign_id, r) for r in recipients]
    return import_rows, db_recipients


def _recipient_from_prepared(campaign_id: uuid.UUID, rec: PreparedRecipient) -> CampaignRecipient:
    names = [n for n in rec.names if n]
    display = ", ".join(names) if names else "Hola"
    return CampaignRecipient(
        campaign_id=campaign_id,
        group_key=rec.group_key,
        to_e164_digits=rec.to_e164_digits,
        button_phone=rec.button_phone,
        display_name=display,
        names_json=names,
        source_lines_json=rec.source_lines,
        entry_code=rec.entry_code,
        status=RecipientStatus.pending,
    )
