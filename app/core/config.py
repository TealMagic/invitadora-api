from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"
    app_version: str = "0.1.0"
    port: int = 8000

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/invitadora"

    internal_api_key: str = "change-me-in-production"
    public_base_url: str = "http://localhost:8000"
    api_internal_url: str = "http://localhost:8000"

    meta_whatsapp_token: str = ""
    meta_phone_number_id: str = "996201250232595"
    meta_graph_version: str = "v20.0"

    default_template_name: str = "confirmacion_registro"
    default_template_language: str = "es_CL"
    default_send_delay_seconds: float = 2.0

    qr_storage_path: str = "./data/qrs"
    log_level: str = "INFO"

    worker_poll_seconds: int = 5
    worker_batch_size: int = 20

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def whatsapp_messages_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.meta_graph_version}/"
            f"{self.meta_phone_number_id}/messages"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
