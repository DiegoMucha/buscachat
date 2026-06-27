from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Buscachat Python"
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/buscachat_dev"
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
