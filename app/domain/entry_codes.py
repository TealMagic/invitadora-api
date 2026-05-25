import hashlib
import re

ENTRY_CODE_LENGTH = 6
ENTRY_CODE_PATTERN = re.compile(r"^[A-Z0-9]{6}$")


def normalize_entry_code(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    return stripped.upper() or None


def validate_entry_code(value: str | None) -> str | None:
    normalized = normalize_entry_code(value)
    if normalized is None:
        return None
    if not ENTRY_CODE_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"entry_code debe tener exactamente {ENTRY_CODE_LENGTH} caracteres alfanuméricos (A-Z, 0-9)"
        )
    return normalized


def generate_entry_code(button_phone: str, name: str) -> str:
    combined = f"{button_phone}_{name}".encode("utf-8")
    hash_hex = hashlib.md5(combined).hexdigest()
    return hash_hex[:ENTRY_CODE_LENGTH].upper()
