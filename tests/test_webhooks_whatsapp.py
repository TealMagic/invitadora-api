import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def webhook_settings():
    with patch("app.api.routes_webhooks.get_settings") as mock_settings:
        settings = MagicMock()
        settings.meta_webhook_verify_token = "test-verify-token"
        settings.meta_app_secret = "test-app-secret"
        mock_settings.return_value = settings
        yield settings


def _sign_body(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


SAMPLE_STATUS_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "123",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "996201250232595"},
                        "statuses": [
                            {
                                "id": "wamid.HBgNNTQ5MTE1",
                                "status": "delivered",
                                "timestamp": "1716652800",
                                "recipient_id": "5491157017999",
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}


class TestWebhookVerify:
    def test_verify_success(self, client, webhook_settings):
        resp = client.get(
            "/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test-verify-token",
                "hub.challenge": "challenge123",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "challenge123"

    def test_verify_wrong_token(self, client, webhook_settings):
        resp = client.get(
            "/v1/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "challenge123",
            },
        )
        assert resp.status_code == 403


class TestWebhookPost:
    def test_invalid_signature_rejected(self, client, webhook_settings):
        body = json.dumps(SAMPLE_STATUS_PAYLOAD).encode()
        resp = client.post(
            "/v1/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
        assert resp.status_code == 403

    def test_valid_signature_processes_status(self, client, webhook_settings):
        body = json.dumps(SAMPLE_STATUS_PAYLOAD).encode()
        signature = _sign_body("test-app-secret", body)

        mock_recipient = MagicMock()
        mock_recipient.id = "550e8400-e29b-41d4-a716-446655440000"

        with patch("app.api.routes_webhooks.RecipientRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_whatsapp_message_id.return_value = mock_recipient
            repo.apply_whatsapp_status.return_value = True

            resp = client.post(
                "/v1/webhooks/whatsapp",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": signature,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["processed"] == 1
        repo.apply_whatsapp_status.assert_called_once()

    def test_no_secret_skips_signature_check(self, client, webhook_settings):
        webhook_settings.meta_app_secret = ""
        body = json.dumps(SAMPLE_STATUS_PAYLOAD).encode()

        with patch("app.api.routes_webhooks.RecipientRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_whatsapp_message_id.return_value = None
            repo.get_by_wa_recipient_id.return_value = None

            resp = client.post(
                "/v1/webhooks/whatsapp",
                content=body,
                headers={"Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert resp.json()["processed"] == 0
