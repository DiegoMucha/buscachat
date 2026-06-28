"""Tests para el webhook directo de WhatsApp (sin n8n).

Cubre:
- Unit tests: extracción de mensaje, motor conversacional (menú, registro,
  búsqueda, comandos globales).
- Integration tests (marcados ``e2e``): endpoint completo vía TestClient,
  incluyendo registro y búsqueda real contra la base de datos.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.whatsapp_base import (
    get_conversation_state as _get_state,
    set_conversation_state as _set_state,
    run_conversation_motor as _motor,
)
from app.routers.green_webhook import _extract_green_message as _extract_message
from app.routers.meta_webhook import _extract_meta_message

# ---------------------------------------------------------------------------
# Mocks para Meta (evitan llamadas reales a la API de Meta)
# ---------------------------------------------------------------------------

# Bytes de prueba que producen un embedding válido con el StubFaceMatcher
_FAKE_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

_meta_messages_sent: list[dict[str, str]] = []
_meta_messages_sent_clear_called = False


def _mock_send_meta_message(chat_id: str, text: str, settings: object, buttons: object = None) -> None:
    """Mock de _send_meta_message: no llama a Meta, solo registra."""
    _meta_messages_sent.append({"chat_id": chat_id, "text": text})


def _mock_download_meta_image(media_id: str, access_token: str, *, timeout: float = 30.0) -> bytes:
    """Mock de _download_meta_image: devuelve bytes de prueba."""
    return _FAKE_IMAGE_BYTES


def _clear_meta_spy() -> None:
    _meta_messages_sent.clear()


def _get_meta_messages_sent() -> list[dict[str, str]]:
    return list(_meta_messages_sent)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_green_body(text: str = "", *, sender: str = "584121234567@c.us", name: str = "Test User") -> dict:
    return {
        "messageData": {
            "typeMessage": "textMessage",
            "textMessageData": {"textMessage": text},
        },
        "senderData": {"sender": sender, "senderName": name},
    }


def _make_green_image_body(image_url: str = "https://example.com/photo.jpg", caption: str = "", *, sender: str = "584121234567@c.us") -> dict:
    return {
        "messageData": {
            "typeMessage": "imageMessage",
            "caption": caption,
            "fileMessageData": {"downloadUrl": image_url},
        },
        "senderData": {"sender": sender},
    }


def _clean_state(chat_id: str = "584121234567@c.us") -> None:
    """Limpia el estado de un chat entre tests."""
    _set_state(chat_id, None)


# ---------------------------------------------------------------------------
# Tests: _extract_message (unitarios — sin DB)
# ---------------------------------------------------------------------------


class TestExtractMessage:
    def test_text_message(self) -> None:
        body = _make_green_body("hola")
        msg = _extract_message(body)
        assert msg["canal"] == "whatsapp"
        assert msg["tipo"] == "texto"
        assert msg["text"] == "hola"
        assert msg["chat_id"] == "584121234567@c.us"
        assert msg["sender"] == "584121234567@c.us"
        assert msg["nombre"] == "Test User"

    def test_image_message(self) -> None:
        body = _make_green_image_body("https://example.com/foto.jpg", "mirá esto")
        msg = _extract_message(body)
        assert msg["tipo"] == "imagen"
        assert msg["imagen_ref"] == "https://example.com/foto.jpg"
        assert msg["text"] == "mirá esto"

    def test_image_without_caption(self) -> None:
        body = _make_green_image_body("https://example.com/foto.jpg", "")
        msg = _extract_message(body)
        assert msg["tipo"] == "imagen"
        assert msg["text"] == ""

    def test_sender_without_at_suffix(self) -> None:
        body = _make_green_body("hola", sender="584121234567")
        msg = _extract_message(body)
        assert msg["chat_id"] == "584121234567@c.us"
        assert msg["sender"] == "584121234567"

    def test_empty_body_produces_safe_defaults(self) -> None:
        body = {}
        msg = _extract_message(body)
        assert msg["text"] == ""
        assert msg["chat_id"] == "@c.us"

    def test_body_with_none_message_data(self) -> None:
        body = {"messageData": None}
        msg = _extract_message(body)
        assert msg["text"] == ""
        assert msg["tipo"] == "texto"


# ---------------------------------------------------------------------------
# Tests: _motor (unitarios — sin DB)
# ---------------------------------------------------------------------------


class TestMotorMenu:
    CHAT = "test_menu@c.us"

    def teardown_method(self) -> None:
        _clean_state(self.CHAT)

    def test_first_message_shows_menu(self) -> None:
        _clean_state(self.CHAT)
        result = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "hola"})
        assert result["accion"] is None
        assert "BuscaChat" in result["respuesta"]
        assert result.get("buttons") == [("1", "Buscar"), ("2", "Registrar"), ("3", "Ayuda")]

    def test_option_1_buscar(self) -> None:
        _clean_state(self.CHAT)
        result = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "1"})
        assert result.get("buttons") == [("1", "📸 Por foto"), ("2", "📝 Por nombre"), ("3", "🪪 Por cédula")]

    def test_option_2_registrar(self) -> None:
        _clean_state(self.CHAT)
        result = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        assert "nombre completo" in result["respuesta"].lower()

    def test_option_3_ayuda(self) -> None:
        _clean_state(self.CHAT)
        result = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "3"})
        assert "ayuda" in result["respuesta"].lower()

    def test_invalid_option_shows_help(self) -> None:
        _clean_state(self.CHAT)
        result = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "999"})
        assert result.get("buttons") is not None  # Muestra menú con botones

    def test_menu_command_resets_state_from_anywhere(self) -> None:
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        result = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "menu"})
        assert "BuscaChat" in result["respuesta"]
        assert result.get("buttons") == [("1", "Buscar"), ("2", "Registrar"), ("3", "Ayuda")]

    def test_cancelar_command_resets_state(self) -> None:
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        result = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "cancelar"})
        assert "BuscaChat" in result["respuesta"]
        assert result.get("buttons") == [("1", "Buscar"), ("2", "Registrar"), ("3", "Ayuda")]

    def test_salir_command_resets_state(self) -> None:
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        result = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "salir"})
        assert "BuscaChat" in result["respuesta"]
        assert result.get("buttons") == [("1", "Buscar"), ("2", "Registrar"), ("3", "Ayuda")]


class TestMotorRegisterFlow:
    CHAT = "test_registro@c.us"

    def teardown_method(self) -> None:
        _clean_state(self.CHAT)

    def test_full_register_flow_emits_accion(self) -> None:
        _clean_state(self.CHAT)
        # 1. Iniciar registro
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        assert "nombre" in r["respuesta"].lower()
        assert r["accion"] is None
        # 2. Dar nombre
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "Juan Pérez"})
        assert "edad" in r["respuesta"].lower()
        # 3-7. Saltar pasos opcionales
        for _ in range(5):  # edad, cedula, ubicacion, descripcion, foto
            _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "omitir"})
        # 8. Dar contacto
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "04141234567"})
        assert "confirm" in r["respuesta"].lower() or "Confirmar" in str(r.get("buttons", ""))
        # 9. Confirmar
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "sí"})
        assert r["accion"] == "registrar_persona"
        assert r["datos"]["nombre"] == "Juan Pérez"
        assert r["datos"]["contacto"] == "04141234567"

    def test_register_cancel_at_confirmation(self) -> None:
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "María"})
        for _ in range(5):  # saltar edad, cedula, ubicacion, descripcion, foto
            _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "omitir"})
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "04141111111"})
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "no"})
        assert "cancelado" in r["respuesta"].lower()
        assert r["accion"] is None

    def test_register_empty_name_asks_again(self) -> None:
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": ""})
        assert "nombre" in r["respuesta"].lower()

    def test_register_preserves_original_case(self) -> None:
        """El nombre se preserva con el casing original del usuario."""
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "ANA MARÍA LÓPEZ"})
        for _ in range(5):  # saltar edad, cedula, ubicacion, descripcion, foto
            _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "omitir"})
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "04141111111"})
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "sí"})
        assert r["datos"]["nombre"] == "ANA MARÍA LÓPEZ"


class TestMotorSearchFlow:
    CHAT = "test_buscar@c.us"

    def teardown_method(self) -> None:
        _clean_state(self.CHAT)

    def test_search_by_name_flow(self) -> None:
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "1"})
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "Carlos"})
        assert r["accion"] == "buscar_por_nombre"
        assert r["datos"]["query"] == "carlos"

    def test_search_by_photo_flow(self) -> None:
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "1"})
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "1"})
        r = _motor({
            "chat_id": self.CHAT,
            "canal": "whatsapp",
            "text": "",
            "tipo": "imagen",
            "imagen_ref": "https://example.com/buscar.jpg",
        })
        assert r["accion"] == "buscar_por_foto"
        assert r["imagen_ref"] == "https://example.com/buscar.jpg"

    def test_state_cleared_after_search_action(self) -> None:
        """Después de emitir una acción, el estado se limpia."""
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "1"})
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "Carlos"})
        # Siguiente mensaje: debe mostrar menú de nuevo
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "hola"})
        assert r.get("buttons") is not None  # menú con botones


class TestMotorEdgeCases:
    CHAT = "test_edge@c.us"

    def teardown_method(self) -> None:
        _clean_state(self.CHAT)

    def test_text_converted_to_lower_for_matching(self) -> None:
        """Comandos son case-insensitive."""
        _clean_state(self.CHAT)
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "MENU"})
        assert r.get("buttons") is not None  # menú con botones

    def test_confirmacion_case_insensitive(self) -> None:
        _clean_state(self.CHAT)
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "2"})      # registrar
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "Pepe"})   # nombre
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "omitir"}) # edad
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "omitir"}) # cedula
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "omitir"}) # ubicacion
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "omitir"}) # descripcion
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "omitir"}) # foto
        _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "555"})    # contacto
        r = _motor({"chat_id": self.CHAT, "canal": "whatsapp", "text": "SÍ"})
        assert r["accion"] == "registrar_persona"

    def test_different_chats_have_independent_state(self) -> None:
        _clean_state("chat_a@c.us")
        _clean_state("chat_b@c.us")
        # Chat A: entra a registrar
        _motor({"chat_id": "chat_a@c.us", "canal": "whatsapp", "text": "2"})
        # Chat B: pide menú
        r_b = _motor({"chat_id": "chat_b@c.us", "canal": "whatsapp", "text": "hola"})
        assert r_b.get("buttons") is not None
        # Chat A: sigue en registro (paso edad después de nombre)
        r_a = _motor({"chat_id": "chat_a@c.us", "canal": "whatsapp", "text": "Juan"})
        assert "edad" in r_a["respuesta"].lower()


# ---------------------------------------------------------------------------
# Tests: integración con FastAPI TestClient (marcados e2e — necesitan DB)
# ---------------------------------------------------------------------------

pytestmark_integration = pytest.mark.e2e


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.e2e
class TestWebhookIntegration:
    CHAT = "integra_webhook@c.us"

    def teardown_method(self) -> None:
        _clean_state(self.CHAT)

    def test_webhook_returns_menu_on_first_message(self, client: TestClient) -> None:
        payload = {
            "messageData": {
                "typeMessage": "textMessage",
                "textMessageData": {"textMessage": "hola"},
            },
            "senderData": {"sender": self.CHAT, "senderName": "Test"},
        }
        response = client.post("/whatsapp/webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == self.CHAT
        assert "BuscaChat" in data["text"]
        assert data["accion"] is None

    def test_webhook_full_register_and_search(self, client: TestClient) -> None:
        """Registra una persona y luego la busca por nombre en otro chat."""
        _clean_state(self.CHAT)
        unique_name = f"IntTest_{id(self)}"
        buscar_chat = "buscar_integra@c.us"

        # ── Registrar (8 pasos: nombre, edad, cédula, ubicación, descripción, foto, contacto, confirmar) ──
        steps = ["2", unique_name] + ["omitir"] * 5 + ["04141111111", "sí"]
        for text in steps:
            resp = client.post("/whatsapp/webhook", json={
                "messageData": {
                    "typeMessage": "textMessage",
                    "textMessageData": {"textMessage": text},
                },
                "senderData": {"sender": self.CHAT},
            })
            assert resp.status_code == 200

        # ── Buscar desde otro chat ──
        _clean_state(buscar_chat)
        client.post("/whatsapp/webhook", json={
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "1"}},
            "senderData": {"sender": buscar_chat},
        })
        client.post("/whatsapp/webhook", json={
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "2"}},
            "senderData": {"sender": buscar_chat},
        })
        resp = client.post("/whatsapp/webhook", json={
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": unique_name}},
            "senderData": {"sender": buscar_chat},
        })
        data = resp.json()
        assert data["accion"] == "buscar_por_nombre"
        assert unique_name.lower() in data["text"].lower(), f"Expected found, got: {data['text']}"

    def test_webhook_search_no_results(self, client: TestClient) -> None:
        _clean_state(self.CHAT)
        client.post("/whatsapp/webhook", json={
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "1"}},
            "senderData": {"sender": self.CHAT},
        })
        client.post("/whatsapp/webhook", json={
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "2"}},
            "senderData": {"sender": self.CHAT},
        })
        resp = client.post("/whatsapp/webhook", json={
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "ZZZ_NO_EXISTE_XYZ"}},
            "senderData": {"sender": self.CHAT},
        })
        data = resp.json()
        assert data["accion"] == "buscar_por_nombre"
        assert "No se encontró" in data["text"]

    def test_webhook_image_without_download_url(self, client: TestClient) -> None:
        """Imagen sin downloadUrl no debería crashear."""
        payload = {
            "messageData": {
                "typeMessage": "imageMessage",
                "caption": "busco a esta persona",
                "fileMessageData": {},
            },
            "senderData": {"sender": self.CHAT},
        }
        response = client.post("/whatsapp/webhook", json=payload)
        assert response.status_code == 200

    def test_webhook_empty_body_shows_menu(self, client: TestClient) -> None:
        response = client.post("/whatsapp/webhook", json={})
        assert response.status_code == 200
        assert "BuscaChat" in response.json()["text"]

    def test_webhook_invalid_json_returns_422(self, client: TestClient) -> None:
        response = client.post("/whatsapp/webhook", data="esto no es json")
        assert response.status_code == 422

    def test_webhook_menu_command_from_anywhere(self, client: TestClient) -> None:
        _clean_state(self.CHAT)
        client.post("/whatsapp/webhook", json={
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "2"}},
            "senderData": {"sender": self.CHAT},
        })
        client.post("/whatsapp/webhook", json={
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "Alguien"}},
            "senderData": {"sender": self.CHAT},
        })
        resp = client.post("/whatsapp/webhook", json={
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "menu"}},
            "senderData": {"sender": self.CHAT},
        })
        assert resp.status_code == 200
        assert "BuscaChat" in resp.json()["text"]


# ============================================================================
# Meta WhatsApp Cloud API tests
# ============================================================================


class TestExtractMetaMessage:
    def test_text_message(self) -> None:
        body = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123456",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{"profile": {"name": "Juan"}, "wa_id": "584121234567"}],
                        "messages": [{
                            "from": "584121234567",
                            "id": "wamid.xxx",
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {"body": "hola mundo"},
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        msg = _extract_meta_message(body)
        assert msg is not None
        assert msg["canal"] == "whatsapp"
        assert msg["tipo"] == "texto"
        assert msg["text"] == "hola mundo"
        assert msg["chat_id"] == "584121234567"
        assert msg["sender"] == "584121234567"
        assert msg["nombre"] == "Juan"

    def test_image_message(self) -> None:
        body = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123456",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{"profile": {"name": "Ana"}, "wa_id": "584121234567"}],
                        "messages": [{
                            "from": "584121234567",
                            "id": "wamid.yyy",
                            "timestamp": "1234567890",
                            "type": "image",
                            "image": {
                                "mime_type": "image/jpeg",
                                "sha256": "abc123",
                                "id": "media_123",
                            },
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        msg = _extract_meta_message(body)
        assert msg is not None
        assert msg["tipo"] == "imagen"
        assert msg["imagen_ref"] == "media_123"

    def test_image_with_caption(self) -> None:
        body = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{"profile": {"name": "Ana"}}],
                        "messages": [{
                            "from": "584121234567",
                            "type": "image",
                            "image": {"id": "media_456", "caption": "¿Conocen a esta persona?"},
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        msg = _extract_meta_message(body)
        assert msg is not None
        assert msg["text"] == "¿Conocen a esta persona?"

    def test_empty_body_returns_none(self) -> None:
        assert _extract_meta_message({}) is None

    def test_no_messages_returns_none(self) -> None:
        body = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{}],
                        "messages": [],
                    },
                }],
            }],
        }
        assert _extract_meta_message(body) is None

    def test_status_notification_returns_none(self) -> None:
        """Notificación de estado (sin messages) no debería crashear."""
        body = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123456",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "+1 555"},
                        "statuses": [{"id": "wamid.zzz", "status": "sent"}],
                    },
                    "field": "messages",
                }],
            }],
        }
        assert _extract_meta_message(body) is None


@pytest.mark.e2e
class TestMetaWebhookIntegration:
    CHAT = "meta_test@c.us"

    @pytest.fixture(autouse=True)
    def _apply_mocks(self, monkeypatch) -> None:
        """Mockea las funciones que llaman a Meta API."""
        import app.routers.meta_webhook as mh

        monkeypatch.setattr(mh, "_send_meta_message", _mock_send_meta_message)
        monkeypatch.setattr(mh, "_download_meta_image", _mock_download_meta_image)

        # Forzar credenciales de Meta para que el webhook procese imágenes
        monkeypatch.setenv("META_ACCESS_TOKEN", "fake-token-for-tests")
        monkeypatch.setenv("META_PHONE_NUMBER_ID", "fake-phone-id")

        # Limpiar el cache de settings (lru_cache) para que lea las nuevas env vars
        from app.config import get_settings
        get_settings.cache_clear()

        _clear_meta_spy()

    def teardown_method(self) -> None:
        _clean_state(self.CHAT)

    # ── helpers ──

    def _meta_text_payload(self, text: str, sender: str | None = None) -> dict:
        chat = sender or self.CHAT
        return {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{"profile": {"name": "Test"}, "wa_id": chat}],
                        "messages": [{
                            "from": chat,
                            "id": "wamid.xxx",
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {"body": text},
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }

    def _meta_image_payload(self, media_id: str = "media_123", caption: str = "", sender: str | None = None) -> dict:
        chat = sender or self.CHAT
        msg: dict = {
            "from": chat,
            "id": "wamid.img",
            "timestamp": "1234567890",
            "type": "image",
            "image": {"mime_type": "image/jpeg", "sha256": "abc", "id": media_id},
        }
        if caption:
            msg["image"]["caption"] = caption
        return {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "contacts": [{"profile": {"name": "Test"}, "wa_id": chat}],
                        "messages": [msg],
                    },
                    "field": "messages",
                }],
            }],
        }

    # ── tests ──

    def test_meta_webhook_verification(self, client: TestClient) -> None:
        from app.config import get_settings
        settings = get_settings()
        token = settings.meta_verify_token

        resp = client.get(
            "/whatsapp/meta-webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": token,
                "hub.challenge": "test_challenge_42",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "test_challenge_42"

    def test_meta_webhook_verification_wrong_token(self, client: TestClient) -> None:
        resp = client.get(
            "/whatsapp/meta-webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "WRONG",
                "hub.challenge": "fail",
            },
        )
        assert resp.status_code == 403

    def test_meta_webhook_text_menu(self, client: TestClient) -> None:
        resp = client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("hola"))
        assert resp.status_code == 200
        assert resp.text == "ok"
        # Verificar que se envió respuesta al usuario
        sent = _get_meta_messages_sent()
        assert len(sent) >= 1
        assert "BuscaChat" in sent[0]["text"]  # menú

    def test_meta_webhook_register_flow(self, client: TestClient) -> None:
        """Registra una persona y verifica que el mensaje de confirmación se envió."""
        _clean_state(self.CHAT)
        unique = f"MetaReg_{id(self)}"

        for step_text in ["2", unique] + ["omitir"] * 5 + ["04141234567", "sí"]:
            resp = client.post("/whatsapp/meta-webhook", json=self._meta_text_payload(step_text))
            assert resp.status_code == 200

        # El último mensaje enviado debe ser de confirmación de registro
        sent = _get_meta_messages_sent()
        confirm_msgs = [m for m in sent if "Registro creado" in m["text"]]
        assert len(confirm_msgs) >= 1

    def test_meta_webhook_search_by_name_found(self, client: TestClient) -> None:
        _clean_state(self.CHAT)
        unique = f"MetaSearch_{id(self)}"

        # Registrar
        for text in ["2", unique] + ["omitir"] * 5 + ["555", "sí"]:
            client.post("/whatsapp/meta-webhook", json=self._meta_text_payload(text))

        # Buscar desde otro chat
        buscar = "meta_buscar@c.us"
        _clean_state(buscar)
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("1", sender=buscar))
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("2", sender=buscar))
        resp = client.post("/whatsapp/meta-webhook", json=self._meta_text_payload(unique, sender=buscar))
        assert resp.status_code == 200

        sent = _get_meta_messages_sent()
        found_msgs = [m for m in sent if unique.lower() in m["text"].lower()]
        assert len(found_msgs) >= 1, f"Expected '{unique}' in messages: {sent}"

    def test_meta_webhook_search_no_results(self, client: TestClient) -> None:
        _clean_state(self.CHAT)
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("1"))
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("2"))
        resp = client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("ZZZNOEXISTE999"))
        assert resp.status_code == 200

        sent = _get_meta_messages_sent()
        not_found = [m for m in sent if "No se encontró" in m["text"]]
        assert len(not_found) >= 1

    def test_meta_webhook_image_register(self, client: TestClient) -> None:
        """Registra con foto: el mock de _download_meta_image devuelve bytes de prueba."""
        _clean_state(self.CHAT)
        unique = f"MetaImg_{id(self)}"

        # ── Registrar (8 pasos) ──
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("2"))
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload(unique))
        for _ in range(5):  # saltar edad, cédula, ubicación, descripción, foto
            client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("omitir"))
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("04141234567"))
        resp = client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("sí"))
        assert resp.status_code == 200

    def test_meta_webhook_image_search(self, client: TestClient) -> None:
        """Registra con foto y busca la misma persona por foto (misma imagen → match 1.0 con stub)."""
        _clean_state(self.CHAT)
        unique = f"MetaImgSrch_{id(self)}"

        # ── Registrar persona con foto (8 pasos) ──
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("2"))
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload(unique))
        # Saltar edad, cédula, ubicación, descripción
        for _ in range(4):
            client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("omitir"))
        # Enviar foto en el paso reg_foto
        resp_img = client.post("/whatsapp/meta-webhook",
                               json=self._meta_image_payload(media_id="img_reg"))
        assert resp_img.status_code == 200
        # Dar contacto
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("555"))
        # Confirmar
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("sí"))
        _clear_meta_spy()  # reseteamos para ver solo los mensajes de búsqueda

        # ── Buscar por foto ──
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("1"))
        client.post("/whatsapp/meta-webhook", json=self._meta_text_payload("1"))
        resp = client.post("/whatsapp/meta-webhook",
                           json=self._meta_image_payload(media_id="img_reg"))
        assert resp.status_code == 200

        sent = _get_meta_messages_sent()
        assert len(sent) >= 4, f"Expected >=4 messages, got: {sent}"
        match_msgs = [m for m in sent if unique.lower() in m["text"].lower()]
        assert len(match_msgs) >= 1, f"No match message in: {sent}"

    def test_meta_webhook_status_notification_no_crash(self, client: TestClient) -> None:
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "+1 555"},
                        "statuses": [{"id": "wamid.zzz", "status": "sent"}],
                    },
                    "field": "messages",
                }],
            }],
        }
        resp = client.post("/whatsapp/meta-webhook", json=payload)
        assert resp.status_code == 200
        assert resp.text == "ok"

    def test_meta_webhook_sender_id_is_chat_id(self) -> None:
        body = {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"value": {
                "messaging_product": "whatsapp",
                "contacts": [{"profile": {"name": "Yo"}}],
                "messages": [{"from": "584121234567", "type": "text", "text": {"body": "menu"}}],
            }, "field": "messages"}]}],
        }
        msg = _extract_meta_message(body)
        assert msg is not None
        assert msg["chat_id"] == "584121234567"
