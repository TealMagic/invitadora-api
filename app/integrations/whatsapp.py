import json
from typing import Tuple

import requests


def send_message(
    session: requests.Session,
    url: str,
    token: str,
    payload: dict,
    timeout_sec: int = 30,
) -> Tuple[bool, int, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        r = session.post(url, headers=headers, json=payload, timeout=timeout_sec)
        status = r.status_code
        text = r.text
        if 200 <= status < 300:
            return True, status, text
        return False, status, text
    except requests.RequestException as e:
        return False, -1, f"RequestException: {e}"


def extract_message_id(response_text: str) -> tuple[str | None, str | None]:
    try:
        data = json.loads(response_text)
        if "messages" in data and data["messages"]:
            msg = data["messages"][0]
            return msg.get("id"), msg.get("message_status")
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return None, None


def is_transient_error(status_code: int) -> bool:
    return status_code == -1 or status_code >= 500
