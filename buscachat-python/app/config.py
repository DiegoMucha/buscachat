from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Buscachat Python"
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:15432/buscachat_dev"
    )
    private_api_token: str = "dev-hackathon-token"

    sos_venezuela_persons_url: str = "https://sosvenezuela2026.com/api/persons/list"
    missing_people_sync_enabled: bool = True
    missing_people_sync_run_on_startup: bool = True
    missing_people_sync_interval_hours: int = 2
    missing_people_sync_page_limit: int = 100
    missing_people_sync_max_pages: int | None = None
    missing_people_sync_retry_attempts: int = 3
    missing_people_sync_retry_backoff_seconds: float = 1.0

    # Bot intake (WhatsApp/Telegram) configuration
    bot_source: str = "whatsapp_bot"

    # Conversation state storage: "in_memory" | "redis"
    conversation_state_store: str = "in_memory"
    redis_url: str = "redis://:your_password_here@localhost:6379/0"
    redis_key_prefix: str = "buscachat:conversation:"
    conversation_state_ttl_seconds: int | None = None

    # Facial recognition
    face_matcher: str = "insightface"  # "insightface" | "stub"
    face_match_threshold: float = 0.35
    face_insightface_model: str = "buffalo_l"

    # WhatsApp notifications (Green API)
    notifier: str = "green_api"  # "green_api" | "null"
    green_api_base_url: str = "https://api.green-api.com"
    green_api_instance_id: str = ""
    green_api_token: str = ""
    image_download_timeout_seconds: float = 30.0

    # Evolution API webhook
    evolution_api_webhook_apikey: str = ""
    evolution_api_send_enabled: bool = False
    evolution_api_base_url: str = "http://localhost:8080"
    evolution_api_instance_name: str = ""
    evolution_api_apikey: str = ""
    evolution_api_connected_jid: str = ""
    evolution_api_send_timeout_seconds: float = 30.0
    evolution_api_send_delay_min_seconds: float = 2.0
    evolution_api_send_delay_max_seconds: float = 6.0

    # Meta WhatsApp Cloud API
    meta_verify_token: str = ""
    meta_access_token: str = ""
    meta_phone_number_id: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
