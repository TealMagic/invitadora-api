import io
import re

import pytest
from PIL import Image

from app.domain.entry_codes import ENTRY_CODE_LENGTH, generate_entry_code, validate_entry_code
from app.domain.guests import (
    GuestRow,
    guests_from_recipient_inputs,
    prepare_recipients,
    read_guests_from_bytes,
)
from app.domain.phones import normalize_ar_phone
from app.schemas import RecipientInput
from app.services.import_service import build_import_entities
from app.domain.qrcode_service import generate_qr_image


class TestNormalizeArPhone:
    def test_mobile_with_country_and_nine(self):
        gk, to, btn, err = normalize_ar_phone("+5491157017999")
        assert err is None
        assert gk == "541157017999"
        assert to == "541157017999"
        assert btn == "1157017999"

    def test_landline_format(self):
        gk1, _, _, _ = normalize_ar_phone("+541157017999")
        gk2, _, _, _ = normalize_ar_phone("11 5701 7999")
        assert gk1 == gk2 == "541157017999"

    def test_double_zero_prefix(self):
        gk, _, _, err = normalize_ar_phone("00541157017999")
        assert err is None
        assert gk == "541157017999"

    def test_invalid_empty(self):
        gk, _, _, err = normalize_ar_phone("")
        assert gk is None
        assert err == "Vacío"


class TestPrepareRecipients:
    def test_groups_duplicates(self):
        guests = [
            GuestRow(2, "Ana", "+5491157017999"),
            GuestRow(3, "Ana B", "11 5701 7999"),
        ]
        recipients, invalid = prepare_recipients(guests)
        assert len(invalid) == 0
        assert len(recipients) == 1
        assert len(recipients[0].names) == 2

    def test_preserves_entry_code_when_grouped(self):
        guests = [
            GuestRow(1, "Juan", "+5491157017999", entry_code="A3B7K9"),
            GuestRow(2, "María", "+5491157017999", entry_code="A3B7K9"),
        ]
        recipients, invalid = prepare_recipients(guests)
        assert len(invalid) == 0
        assert len(recipients) == 1
        assert recipients[0].entry_code == "A3B7K9"

    def test_entry_code_conflict_keeps_first(self):
        guests = [
            GuestRow(1, "Juan", "+5491157017999", entry_code="AAAAAA"),
            GuestRow(2, "María", "+5491157017999", entry_code="BBBBBB"),
        ]
        recipients, invalid = prepare_recipients(guests)
        assert len(invalid) == 0
        assert len(recipients) == 1
        assert recipients[0].entry_code == "AAAAAA"


class TestGuestsFromRecipientInputs:
    def test_maps_json_to_guest_rows(self):
        items = [
            RecipientInput(display_name="Juan Pérez", button_phone="+5491155551234", entry_code="A3B7K9"),
        ]
        rows = guests_from_recipient_inputs(items)
        assert len(rows) == 1
        assert rows[0].line_no == 1
        assert rows[0].name == "Juan Pérez"
        assert rows[0].raw_phone == "+5491155551234"
        assert rows[0].entry_code == "A3B7K9"


class TestBuildImportEntities:
    def test_persists_entry_code_on_recipient(self):
        import uuid

        guests = [
            GuestRow(1, "Juan", "+5491157017999", entry_code="A3B7K9"),
        ]
        _, recipients = build_import_entities(uuid.uuid4(), guests)
        assert len(recipients) == 1
        assert recipients[0].entry_code == "A3B7K9"
        assert recipients[0].display_name == "Juan"


class TestEntryCode:
    def test_format(self):
        code = generate_entry_code("1157017999", "Ana")
        assert re.match(rf"^[A-F0-9]{{{ENTRY_CODE_LENGTH}}}$", code)

    def test_rejects_non_six_char_codes(self):
        with pytest.raises(ValueError):
            validate_entry_code("PEDG3AVU")

    def test_schema_rejects_eight_char_entry_code(self):
        with pytest.raises(Exception):
            RecipientInput(
                display_name="Juan",
                button_phone="+5491155551234",
                entry_code="PEDG3AVU",
            )


class TestQrImage:
    def test_jpg_dimensions(self):
        data = generate_qr_image("A3B7K9")
        img = Image.open(io.BytesIO(data))
        assert img.format == "JPEG"
        assert img.size == (1125, 600)


class TestReadGuests:
    def test_detects_columns(self):
        csv_data = b"nombre,telefono\nJuan,1157017999\n"
        rows = read_guests_from_bytes(csv_data)
        assert len(rows) == 1
        assert rows[0].name == "Juan"

    def test_missing_columns_raises(self):
        csv_data = b"foo,bar\n1,2\n"
        with pytest.raises(Exception):
            read_guests_from_bytes(csv_data)
