from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import InferenceEvent
from ..schemas import MetricsSummary
from ..services.metrics import compute_metrics

router = APIRouter(prefix="/v1", tags=["metrics"])


@router.get("/metrics/summary", response_model=MetricsSummary)
async def metrics_summary(
    window_minutes: int = Query(default=60, ge=5, le=1440),
    session: AsyncSession = Depends(get_db),
):
    return await compute_metrics(session, window_minutes=window_minutes)


@router.get("/inference-events")
async def list_events(
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(InferenceEvent).order_by(InferenceEvent.started_at.desc()).limit(limit)
    rows = list((await session.scalars(stmt)).all())
    return [
        {
            "id": str(r.id),
            "event_id": r.event_id,
            "conversation_id": r.conversation_id,
            "provider": r.provider,
            "model": r.model,
            "status": r.status,
            "latency_ms": r.latency_ms,
            "ttft_ms": r.ttft_ms,
            "total_tokens": r.total_tokens,
            "streaming": r.streaming,
            "input_preview": r.input_preview,
            "output_preview": r.output_preview,
            "error_type": r.error_type,
            "started_at": r.started_at.isoformat() if r.started_at else None,
        }
        for r in rows
    ]