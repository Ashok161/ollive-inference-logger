from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_db
from ..schemas import InferenceLogIn, IngestResponse
from ..services.ingest import dead_letter, persist_inference_event
from ..services.queue import event_queue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["ingestion"])


def verify_ingest_key(x_ingest_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.ingestion_api_key and x_ingest_key != settings.ingestion_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ingest key")


@router.post("/ingest", response_model=IngestResponse)
async def ingest_log(
    payload: InferenceLogIn,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_ingest_key),
) -> IngestResponse:
    """
    Near-real-time ingestion endpoint.

    Validates payload, publishes to Redis Streams (event bus), and also
    persists synchronously for low-latency dashboard visibility.
    """
    settings = get_settings()
    body = payload.model_dump(mode="json")
    queued = False
    try:
        await event_queue.publish(body)
        queued = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Queue publish failed, falling back to sync persist: %s", exc)

    try:
        await persist_inference_event(session, payload, redact=settings.pii_redaction_enabled)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to persist inference event")
        try:
            await dead_letter(session, body, str(exc))
        except Exception:  # noqa: BLE001
            pass
        if not queued:
            raise HTTPException(status_code=500, detail="Ingestion failed") from exc

    return IngestResponse(accepted=True, event_id=payload.event_id, queued=queued)


@router.post("/ingest/batch", response_model=list[IngestResponse])
async def ingest_batch(
    payloads: list[InferenceLogIn],
    session: AsyncSession = Depends(get_db),
    _: None = Depends(verify_ingest_key),
) -> list[IngestResponse]:
    results = []
    for payload in payloads:
        results.append(await ingest_log(payload, session, _))
    return results