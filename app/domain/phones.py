import re
from typing import Optional, Tuple

import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException


def sanitize_phone(raw: str) -> str:
    s = (raw or "").strip()
    s = s.replace("\u200e", "").replace("\u200f", "")
    s = s.replace("\u202a", "").replace("\u202b", "").replace("\u202c", "").replace("\u202d", "").replace("\u202e", "")
    s = re.sub(r"[^\d+]", "", s)
    return s


def normalize_ar_phone(raw_phone: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Devuelve: (group_key, to_e164_digits, button_phone, error_reason)
    """
    s = sanitize_phone(raw_phone)
    if not s:
        return None, None, None, "Vacío"

    if s.startswith("00"):
        s = "+" + s[2:]

    try:
        if s.startswith("+"):
            pn = phonenumbers.parse(s, None)
        else:
            pn = phonenumbers.parse(s, "AR")
    except NumberParseException as e:
        return None, None, None, f"No se pudo parsear ({e})"

    if not phonenumbers.is_valid_number(pn):
        return None, None, None, "Número inválido según phonenumbers"

    if phonenumbers.region_code_for_number(pn) != "AR":
        return None, None, None, "No parece ser un número de Argentina (AR)"

    e164 = phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
    e164_digits = e164.replace("+", "")

    if not e164_digits.isdigit():
        return None, None, None, "E.164 no numérico"
    if len(e164_digits) < 11 or len(e164_digits) > 15:
        return None, None, None, "Longitud E.164 fuera de rango"

    btn = e164_digits
    if btn.startswith("54"):
        btn = btn[2:]
    if btn.startswith("9"):
        btn = btn[1:]

    if not btn.isdigit():
        return None, None, None, "button_phone no numérico"
    if len(btn) < 10:
        return None, None, None, "button_phone demasiado corto (esperable >=10 en AR)"

    group_key = "54" + btn
    to_e164_digits = group_key

    return group_key, to_e164_digits, btn, None
