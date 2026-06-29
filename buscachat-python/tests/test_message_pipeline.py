from app.adapters.green_api import NullNotifier
from app.config import Settings
from app.face.stub import StubFaceMatcher
from app.messaging.pipeline import run_message_pipeline
from app.messaging.session_store import InMemoryConversationStateStore
from app.messaging.types import GenericInboundMessage, MessageSource
from app.models import MissingPerson


def test_name_search_returns_up_to_ten_informative_results(monkeypatch) -> None:
    people = [
        MissingPerson(
            id=index,
            source="test",
            external_id=str(index),
            full_name=f"Maria Persona {index}",
            status="found" if index == 2 else "missing",
            last_known_location=f"Zona {index}",
            photo_url=f"https://example.test/persona-{index}.jpg",
        )
        for index in range(1, 11)
    ]

    def fake_search_by_name_matches(session, name: str, *, limit: int):
        assert name == "maria"
        assert limit == 10
        return people

    monkeypatch.setattr(
        "app.services.bot_intake.search_by_name_matches",
        fake_search_by_name_matches,
    )
    monkeypatch.setattr(
        "app.messaging.pipeline._get_linked_bot_reports_by_person_id",
        lambda session, person_ids: {},
    )

    store = InMemoryConversationStateStore()
    store.set_state("chat-1", {"paso": "buscar_nombre"})
    message = GenericInboundMessage(
        source=MessageSource.WEB,
        sender_id="user-1",
        chat_id="chat-1",
        text="Maria",
    )

    outbound = run_message_pipeline(
        message,
        session=object(),
        matcher=StubFaceMatcher(),
        notifier=NullNotifier(),
        settings=Settings(face_matcher="stub", notifier="null"),
        conversation_store=store,
    )

    assert outbound.source == MessageSource.WEB
    assert "Mostrando 10 coincidencias" in outbound.text
    assert "✅ Encontrada" in outbound.text
    assert "❌ No encontrada" in outbound.text
    assert "👤 Nombre: *Maria Persona 1*" in outbound.text
    assert "📍 Direccion/ubicacion: Zona 1" in outbound.text
    assert "🖼 Imagen: https://example.test/persona-1.jpg" in outbound.text
    assert "Maria Persona 10" in outbound.text
    assert "Maria Persona 11" not in outbound.text
    assert [button.id for button in outbound.buttons] == ["menu"]
