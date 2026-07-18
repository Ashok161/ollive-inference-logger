"""
Event-based ingestion worker.

Consumes inference log events from Redis Streams, validates/parses them,
applies PII redaction, and upserts into Postgres.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import redis
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ollive.worker")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url_sync: str = "postgresql://ollive:ollive@localhost:5432/ollive"
    redis_url: str = "redis://localhost:6379/0"
    ingestion_queue: str = "inference_logs"
    pii_redaction_enabled: bool = True
    worker_group: str = "workers"
    worker_name: str = "worker-1"


settings = Settings()


class Base(DeclarativeBase):
    pass


class InferenceEvent(Base):
    __tablename__ = "inference_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    streaming: Mapped[bool] = mapped_column(Boolean, default=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    input_preview: Mapped[str] = mapped_column(Text, default="")
    output_preview: Mapped[str] = mapped_column(Text, default="")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestDeadLetter(Base):
    __tablename__ = "ingest_dead_letters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# Import shared PII helpers (Docker copies them under /app/app/...)
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
try:
    from app.services.pii import redact_pii  # type: ignore
except Exception:  # noqa: BLE001
    import re

    EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

    def redact_pii(text: str, enabled: bool = True) -> str:  # type: ignore
        if not enabled or not text:
            return text
        return EMAIL_RE.sub("[REDACTED_EMAIL]", text)


RUNNING = True


def handle_signal(*_args):
    global RUNNING
    RUNNING = False


def parse_dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def process_payload(session: Session, payload: dict) -> None:
    event_id = payload.get("event_id")
    if not event_id:
        raise ValueError("missing event_id")

    existing = session.scalar(select(InferenceEvent).where(InferenceEvent.event_id == event_id))
    if existing:
        return

    usage = payload.get("usage") or {}
    redact = settings.pii_redaction_enabled
    event = InferenceEvent(
        event_id=event_id,
        request_id=payload.get("request_id") or event_id,
        conversation_id=payload.get("conversation_id"),
        session_id=payload.get("session_id"),
        provider=payload["provider"],
        model=payload["model"],
        status=payload.get("status") or "success",
        error_type=payload.get("error_type"),
        error_message=payload.get("error_message"),
        latency_ms=float(payload.get("latency_ms") or 0),
        ttft_ms=payload.get("ttft_ms"),
        streaming=bool(payload.get("streaming")),
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        total_tokens=int(
            usage.get("total_tokens")
            or (int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0))
        ),
        input_preview=redact_pii(payload.get("input_preview") or "", enabled=redact),
        output_preview=redact_pii(payload.get("output_preview") or "", enabled=redact),
        message_count=int(payload.get("message_count") or 0),
        started_at=parse_dt(payload.get("started_at")) or datetime.now(timezone.utc),
        finished_at=parse_dt(payload.get("finished_at")),
        raw_payload=payload,
    )
    session.add(event)
    session.commit()


def ensure_group(r: redis.Redis) -> None:
    try:
        r.xgroup_create(settings.ingestion_queue, settings.worker_group, id="0", mkstream=True)
        logger.info("Created consumer group %s", settings.worker_group)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def main() -> None:
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
    Base.metadata.create_all(engine)

    r = redis.from_url(settings.redis_url, decode_responses=True)
    ensure_group(r)
    logger.info(
        "Worker listening on stream=%s group=%s",
        settings.ingestion_queue,
        settings.worker_group,
    )

    while RUNNING:
        try:
            resp = r.xreadgroup(
                groupname=settings.worker_group,
                consumername=settings.worker_name,
                streams={settings.ingestion_queue: ">"},
                count=20,
                block=5000,
            )
            if not resp:
                continue
            with Session(engine) as session:
                for _stream, messages in resp:
                    for msg_id, fields in messages:
                        raw = fields.get("payload") or "{}"
                        try:
                            payload = json.loads(raw)
                            process_payload(session, payload)
                            r.xack(settings.ingestion_queue, settings.worker_group, msg_id)
                        except (ValidationError, ValueError, KeyError, json.JSONDecodeError) as exc:
                            logger.warning("Bad payload %s: %s", msg_id, exc)
                            session.add(
                                IngestDeadLetter(
                                    payload={"raw": raw},
                                    error=str(exc)[:2000],
                                )
                            )
                            session.commit()
                            r.xack(settings.ingestion_queue, settings.worker_group, msg_id)
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("Failed processing %s: %s", msg_id, exc)
                            time.sleep(1)
        except redis.ConnectionError:
            logger.warning("Redis connection lost; retrying…")
            time.sleep(2)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Worker loop error: %s", exc)
            time.sleep(2)

    logger.info("Worker shutting down")


if __name__ == "__main__":
    main()