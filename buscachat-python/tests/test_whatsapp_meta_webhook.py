from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.routers.whatsapp_meta_webhook import router


def test_meta_webhook_verification_echoes_challenge() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(meta_verify_token="verify-me")

    client = TestClient(app)
    response = client.get(
        "/whatsapp-meta-webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge-123"
    assert response.headers["content-type"].startswith("text/plain")


def test_meta_webhook_verification_rejects_wrong_token() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(meta_verify_token="verify-me")

    client = TestClient(app)
    response = client.get(
        "/whatsapp-meta-webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 403
    assert response.text == "Verification failed"
