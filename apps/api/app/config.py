from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://ollive:ollive@localhost:5432/ollive"
    database_url_sync: str = "postgresql://ollive:ollive@localhost:5432/ollive"
    redis_url: str = "redis://localhost:6379/0"
    ingestion_queue: str = "inference_logs"
    ingestion_api_key: str = "dev-ingest-key"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    default_provider: str = "groq"
    default_model: str = "llama-3.3-70b-versatile"
    context_window_messages: int = 12
    pii_redaction_enabled: bool = True
    ingestion_url: str = "http://localhost:8000/v1/ingest"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()