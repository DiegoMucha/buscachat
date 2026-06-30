from app.adapters.venezuela_te_busca import VenezuelaTeBuscaPerson, VenezuelaTeBuscaSearchResult
from app.config import Settings
from app.face.stub import StubFaceMatcher
from app.messaging.notifier import NullNotifier
from app.messaging.pipeline import run_message_pipeline
from app.messaging.session_store import InMemoryConversationStateStore
from app.messaging.types import GenericInboundMessage, MessageSource


def test_text_search_returns_up_to_ten_informative_results(monkeypatch) -> None:
    people = [
        VenezuelaTeBuscaPerson(
            id=str(index),
            firstName=f"Example Person {index}",
            status="found" if index == 2 else "missing",
            idNumber=f"TEST-{index:04d}",
            lastSeen=f"Sample Zone {index}",
            description=f"Synthetic description {index}",
            photoUrl=f"https://example.test/persona-{index}.jpg",
            foundNote="Fallecido" if index == 2 else None,
            hospitalStatus="deceased" if index == 2 else None,
        )
        for index in range(1, 11)
    ]

    def fake_search_venezuela_te_busca(query: str, *, base_url: str, timeout: float, limit: int):
        assert query == "example"
        assert base_url == "https://venezuelatebusca.com"
        assert timeout == 20.0
        assert limit == 10
        return VenezuelaTeBuscaSearchResult(query="example", persons=people, total_count=12)

    monkeypatch.setattr(
        "app.messaging.pipeline.search_venezuela_te_busca",
        fake_search_venezuela_te_busca,
    )

    store = InMemoryConversationStateStore()
    store.set_state("chat-1", {"paso": "menu"})
    message = GenericInboundMessage(
        source=MessageSource.WEB,
        sender_id="user-1",
        chat_id="chat-1",
        text="example",
    )

    outbound = run_message_pipeline(
        message,
        session=object(),
        matcher=StubFaceMatcher(),
        notifier=NullNotifier(),
        settings=Settings(face_matcher="stub"),
        conversation_store=store,
    )

    assert outbound.source == MessageSource.WEB
    assert outbound.action == "buscar_por_query"
    assert "Mostrando 10 de 12 coincidencias" in outbound.text
    assert "*Estado:* Encontrada" in outbound.text
    assert "*Estado:* No encontrada" in outbound.text
    assert "*Nombre:* Example Person 1" in outbound.text
    assert "*Ubicación:* Sample Zone 1" in outbound.text
    assert "*Orígen:* https://venezuelatebusca.com/?person=1" in outbound.text
    assert "*Cédula:* TEST-0001" in outbound.text
    assert "*Nota de estado:* Fallecido" in outbound.text
    assert "*Foto:*" not in outbound.text
    assert "https://example.test/persona-1.jpg" not in outbound.text
    assert "*Descripcion:*" not in outbound.text
    assert "*Descripción:*" not in outbound.text
    assert "Example Person 10" in outbound.text
    assert "Example Person 11" not in outbound.text
    assert [(button.id, button.title) for button in outbound.buttons] == [
        ("buscar", "Buscar persona"),
        ("menu", "Menu principal"),
    ]


def test_menu_text_returns_menu_without_external_search(monkeypatch) -> None:
    def fail_search_venezuela_te_busca(*args, **kwargs):
        raise AssertionError("menu should not be treated as a search query")

    monkeypatch.setattr(
        "app.messaging.pipeline.search_venezuela_te_busca",
        fail_search_venezuela_te_busca,
    )

    store = InMemoryConversationStateStore()
    store.set_state("chat-1", {"paso": "menu"})
    message = GenericInboundMessage(
        source=MessageSource.META,
        sender_id="user-1",
        chat_id="chat-1",
        text="menu",
    )

    outbound = run_message_pipeline(
        message,
        session=object(),
        matcher=StubFaceMatcher(),
        notifier=NullNotifier(),
        settings=Settings(face_matcher="stub"),
        conversation_store=store,
    )

    assert outbound.action is None
    assert "BuscaChat" in outbound.text
    assert [(button.id, button.title) for button in outbound.buttons] == [
        ("1", "Buscar persona"),
        ("2", "Registrar persona"),
        ("3", "Ayuda"),
    ]
