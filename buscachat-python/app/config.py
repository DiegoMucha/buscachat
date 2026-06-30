from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Buscachat Python"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:15432/buscachat_dev"

    venezuela_te_busca_base_url: str = "https://venezuelatebusca.com"
    venezuela_te_busca_timeout_seconds: float = 20.0

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

    image_download_timeout_seconds: float = 30.0

    # Meta WhatsApp Cloud API
    meta_graph_api_version: str = "v25.0"
    meta_verify_token: str = ""
    meta_app_secret: str = ""
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
