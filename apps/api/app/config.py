from functools import lru_cache

from pydantic import model_validator
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
    default_model: str = "openai/gpt-oss-20b"
    context_window_messages: int = 12
    pii_redaction_enabled: bool = True
    ingestion_url: str = "http://localhost:8000/v1/ingest"
    embed_worker: bool = False

    @model_validator(mode="after")
    def normalize_db_urls(self) -> "Settings":
        # Managed Postgres (Neon/Render) often exposes postgresql:// — async needs +asyncpg.
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg prefers ssl=require over sslmode=require
        url = url.replace("sslmode=require", "ssl=require")
        url = url.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("channel_binding=require", "")
        sync = self.database_url_sync
        if sync.startswith("postgres://"):
            sync = sync.replace("postgres://", "postgresql://", 1)
        sync = sync.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("channel_binding=require", "")
        self.database_url = url
        self.database_url_sync = sync
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
