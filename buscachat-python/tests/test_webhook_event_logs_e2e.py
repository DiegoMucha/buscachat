from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlmodel import Session, delete, select
from testcontainers.postgres import PostgresContainer

from app.config import Settings, get_settings
from app.database import run_migrations
from app.database import get_session
from app.models import WebhookEventLog
from app.routers.whatsapp_evolution_api_webhook import router


pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg18") as postgres:
        yield postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )


def test_webhook_event_log_migration_supports_capture_list_and_delete(
    postgres_url: str,
) -> None:
    engine = create_engine(postgres_url, pool_pre_ping=True)
    run_migrations(engine)

    with Session(engine) as session:
        event_log = WebhookEventLog(
            method="POST",
            url="https://example.test/whatsapp-evolution-api-webhook?source=n8n",
            path="/whatsapp-evolution-api-webhook",
            source_ip="203.0.113.10",
            headers={"content-type": "application/json"},
            query_params={"source": "n8n"},
            body={"event": "message", "payload": {"text": "hola"}},
        )
        session.add(event_log)
        session.commit()
        session.refresh(event_log)

        logs = session.exec(select(WebhookEventLog)).all()
        assert len(logs) == 1
        assert logs[0].body == {"event": "message", "payload": {"text": "hola"}}

        result = session.exec(delete(WebhookEventLog))
        session.commit()

        assert result.rowcount == 1
        assert session.exec(select(WebhookEventLog)).all() == []


def test_webhook_event_log_routes_capture_list_and_delete(postgres_url: str) -> None:
    engine = create_engine(postgres_url, pool_pre_ping=True)
    run_migrations(engine)

    app = FastAPI()
    app.include_router(router)

    def session_override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: Settings(
        private_api_token="secret",
        evolution_api_webhook_apikey="evolution-secret",
        face_matcher="stub",
        notifier="null",
    )

    with TestClient(app) as client:
        capture_response = client.post(
            "/whatsapp-evolution-api-webhook?source=n8n&source=meta",
            headers={
                "x-forwarded-for": "203.0.113.20, 10.0.0.1",
                "x-custom-event": "message",
            },
            json={
                "data": {
                    "key": {
                        "id": "msg-1",
                        "fromMe": False,
                        "remoteJid": "59175034784@s.whatsapp.net",
                    },
                    "message": {"conversation": "hola"},
                    "messageType": "conversation",
                },
                "apikey": "evolution-secret",
                "event": "messages.upsert",
            },
        )
        assert capture_response.status_code == 200
        log_id = capture_response.json()["log_id"]

        list_response = client.get("/whatsapp-evolution-api-webhook/logs")
        assert list_response.status_code == 200
        logs = list_response.json()
        assert len(logs) == 1
        assert logs[0]["id"] == log_id
        assert logs[0]["method"] == "POST"
        assert logs[0]["source_ip"] == "203.0.113.20"
        assert logs[0]["headers"]["x-custom-event"] == "message"
        assert logs[0]["query_params"] == {"source": ["n8n", "meta"]}
        assert logs[0]["body"]["apikey"] == "***redacted***"
        assert logs[0]["body"]["data"]["key"]["remoteJid"] == "59175034784@s.whatsapp.net"

        unauthenticated_delete = client.delete("/whatsapp-evolution-api-webhook/logs")
        assert unauthenticated_delete.status_code == 401

        delete_response = client.delete(
            "/whatsapp-evolution-api-webhook/logs",
            headers={"x-api-token": "secret"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json() == {"ok": True, "deleted": 1}
        assert client.get("/whatsapp-evolution-api-webhook/logs").json() == []
