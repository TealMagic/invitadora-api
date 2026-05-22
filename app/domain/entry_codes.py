import hashlib


def generate_entry_code(button_phone: str, name: str) -> str:
    combined = f"{button_phone}_{name}".encode("utf-8")
    hash_hex = hashlib.md5(combined).hexdigest()
    code = hash_hex[:5].upper()
    return f"ENT-{code}"
