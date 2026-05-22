import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "event": record.getMessage(),
        }
        for key in ("campaign_id", "recipient_id", "job_id", "detail"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(service: str, level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service=service))
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def log_extra(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    campaign_id: str | None = None,
    recipient_id: str | None = None,
    job_id: str | None = None,
    detail: str | None = None,
) -> None:
    logger.log(
        level,
        event,
        extra={
            "campaign_id": campaign_id,
            "recipient_id": recipient_id,
            "job_id": job_id,
            "detail": detail,
        },
    )
