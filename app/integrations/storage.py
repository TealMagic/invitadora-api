from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.core.config import Settings, get_settings


class StorageBackend(Protocol):
    def save_qr(self, campaign_id: UUID, recipient_id: UUID, image_bytes: bytes) -> str:
        ...

    def get_qr_path(self, campaign_id: UUID, recipient_id: UUID) -> Path | None:
        ...

    def public_url(self, campaign_id: UUID, recipient_id: UUID) -> str:
        ...


class LocalVolumeStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_path = Path(self.settings.qr_storage_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _relative_path(self, campaign_id: UUID, recipient_id: UUID) -> Path:
        return Path(str(campaign_id)) / f"{recipient_id}.jpg"

    def save_qr(self, campaign_id: UUID, recipient_id: UUID, image_bytes: bytes) -> str:
        rel = self._relative_path(campaign_id, recipient_id)
        full = self.base_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(image_bytes)
        return self.public_url(campaign_id, recipient_id)

    def get_qr_path(self, campaign_id: UUID, recipient_id: UUID) -> Path | None:
        full = self.base_path / self._relative_path(campaign_id, recipient_id)
        return full if full.is_file() else None

    def public_url(self, campaign_id: UUID, recipient_id: UUID) -> str:
        base = self.settings.public_base_url.rstrip("/")
        return f"{base}/qrs/{campaign_id}/{recipient_id}.jpg"


def get_storage(settings: Settings | None = None) -> LocalVolumeStorage:
    return LocalVolumeStorage(settings)
