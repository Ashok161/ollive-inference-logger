from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import IngestDeadLetter, InferenceEvent
from ..schemas import InferenceLogIn
from .pii import redact_pii

logger = logging.getLogger(__name__)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


async def persist_inference_event(
    session: AsyncSession,
    payload: dict[str, Any] | InferenceLogIn,
    *,
    redact: bool = True,
) -> InferenceEvent:
    data = payload if isinstance(payload, InferenceLogIn) else InferenceLogIn.model_validate(payload)

    existing = await session.scalar(
        select(InferenceEvent).where(InferenceEvent.event_id == data.event_id)
    )
    if existing:
        return existing

    usage = data.usage
    event = InferenceEvent(
        event_id=data.event_id,
        request_id=data.request_id,
        conversation_id=data.conversation_id,
        session_id=data.session_id,
        provider=data.provider,
        model=data.model,
        status=data.status,
        error_type=data.error_type,
        error_message=data.error_message,
        latency_ms=data.latency_ms,
        ttft_ms=data.ttft_ms,
        streaming=data.streaming,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens or (usage.prompt_tokens + usage.completion_tokens),
        input_preview=redact_pii(data.input_preview, enabled=redact),
        output_preview=redact_pii(data.output_preview, enabled=redact),
        message_count=data.message_count,
        started_at=data.started_at,
        finished_at=data.finished_at,
        raw_payload=data.model_dump(mode="json"),
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def dead_letter(session: AsyncSession, payload: dict[str, Any], error: str) -> None:
    session.add(IngestDeadLetter(payload=payload, error=error[:2000]))
    await session.commit()