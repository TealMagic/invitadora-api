import csv
import hashlib
import io
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.domain.phones import normalize_ar_phone


NAME_COLUMNS = {"nombre completo", "nombre", "invitado", "full name", "name"}
PHONE_COLUMNS = {"celular", "telefono", "teléfono", "phone", "mobile"}


class ImportColumnError(Exception):
    def __init__(self, fieldnames: Optional[List[str]]) -> None:
        self.fieldnames = fieldnames
        super().__init__(f"No se encontraron columnas requeridas. Fieldnames={fieldnames}")


@dataclass
class GuestRow:
    line_no: int
    name: str
    raw_phone: str


@dataclass
class PreparedRecipient:
    group_key: str
    to_e164_digits: str
    button_phone: str
    names: List[str]
    source_lines: List[int]


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        if "\t" in sample:
            return "\t"
        return ","


def read_guests_from_bytes(
    content: bytes,
    delimiter: Optional[str] = None,
    has_header: bool = True,
) -> List[GuestRow]:
    text = content.decode("utf-8-sig")
    if delimiter is None:
        delimiter = _detect_delimiter(text[:4096])

    if has_header:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        name_key = None
        phone_key = None
        for k in reader.fieldnames or []:
            kl = (k or "").strip().lower()
            if kl in NAME_COLUMNS:
                name_key = k
            if kl in PHONE_COLUMNS:
                phone_key = k

        if not name_key or not phone_key:
            raise ImportColumnError(list(reader.fieldnames or []))

        rows: List[GuestRow] = []
        for idx, row in enumerate(reader, start=2):
            name = (row.get(name_key) or "").strip().strip('"')
            phone = (row.get(phone_key) or "").strip().strip('"')
            if name or phone:
                rows.append(GuestRow(line_no=idx, name=name, raw_phone=phone))
        return rows

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for idx, row in enumerate(reader, start=1):
        if len(row) < 2:
            continue
        name = (row[0] or "").strip().strip('"')
        phone = (row[1] or "").strip().strip('"')
        if name or phone:
            rows.append(GuestRow(line_no=idx, name=name, raw_phone=phone))
    return rows


def prepare_recipients(guests: List[GuestRow]) -> tuple[List[PreparedRecipient], List[tuple[GuestRow, str]]]:
    grouped: Dict[str, PreparedRecipient] = {}
    invalid: List[tuple[GuestRow, str]] = []

    for g in guests:
        group_key, to_e164_digits, btn, err = normalize_ar_phone(g.raw_phone)
        if err:
            invalid.append((g, err))
            continue

        rec = grouped.get(group_key)
        if not rec:
            grouped[group_key] = PreparedRecipient(
                group_key=group_key,
                to_e164_digits=to_e164_digits,
                button_phone=btn,
                names=[g.name] if g.name else [],
                source_lines=[g.line_no],
            )
        else:
            if g.name:
                rec.names.append(g.name)
            rec.source_lines.append(g.line_no)

    recipients = sorted(grouped.values(), key=lambda r: r.group_key)
    return recipients, invalid
