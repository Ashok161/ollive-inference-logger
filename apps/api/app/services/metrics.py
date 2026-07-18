from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import InferenceEvent
from ..schemas import MetricsSummary


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[idx]


def _bucket_key(dt: datetime, minutes: int = 5) -> str:
    minute = (dt.minute // minutes) * minutes
    bucket = dt.replace(minute=minute, second=0, microsecond=0)
    return bucket.isoformat()


async def compute_metrics(session: AsyncSession, window_minutes: int = 60) -> MetricsSummary:
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    stmt: Select[Any] = select(InferenceEvent).where(InferenceEvent.started_at >= since)
    rows = list((await session.scalars(stmt)).all())

    total = len(rows)
    success = sum(1 for r in rows if r.status == "success")
    errors = sum(1 for r in rows if r.status == "error")
    cancelled = sum(1 for r in rows if r.status == "cancelled")
    latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
    ttfts = [r.ttft_ms for r in rows if r.ttft_ms is not None]
    tokens = sum(r.total_tokens or 0 for r in rows)

    by_provider: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    latency_buckets: dict[str, list[float]] = {}
    throughput_buckets: dict[str, int] = {}
    error_buckets: dict[str, int] = {}

    for r in rows:
        bp = by_provider.setdefault(
            r.provider, {"provider": r.provider, "count": 0, "errors": 0, "avg_latency_ms": 0.0}
        )
        bp["count"] += 1
        if r.status == "error":
            bp["errors"] += 1
        bp["_lat"] = bp.get("_lat", []) + [r.latency_ms]

        bm = by_model.setdefault(
            r.model, {"model": r.model, "provider": r.provider, "count": 0, "errors": 0}
        )
        bm["count"] += 1
        if r.status == "error":
            bm["errors"] += 1

        key = _bucket_key(r.started_at)
        latency_buckets.setdefault(key, []).append(r.latency_ms)
        throughput_buckets[key] = throughput_buckets.get(key, 0) + 1
        if r.status == "error":
            error_buckets[key] = error_buckets.get(key, 0) + 1

    for bp in by_provider.values():
        vals = bp.pop("_lat", [])
        bp["avg_latency_ms"] = round(mean(vals), 2) if vals else 0.0

    latency_series = [
        {"ts": k, "avg_latency_ms": round(mean(v), 2), "p95_latency_ms": round(_percentile(v, 95), 2)}
        for k, v in sorted(latency_buckets.items())
    ]
    throughput_series = [
        {"ts": k, "requests": v} for k, v in sorted(throughput_buckets.items())
    ]
    error_series = [{"ts": k, "errors": v} for k, v in sorted(error_buckets.items())]

    rpm = (total / window_minutes) if window_minutes else 0.0

    return MetricsSummary(
        window_minutes=window_minutes,
        total_requests=total,
        success_count=success,
        error_count=errors,
        cancelled_count=cancelled,
        error_rate=round((errors / total) if total else 0.0, 4),
        avg_latency_ms=round(mean(latencies), 2) if latencies else 0.0,
        p95_latency_ms=round(_percentile(latencies, 95), 2) if latencies else 0.0,
        avg_ttft_ms=round(mean(ttfts), 2) if ttfts else 0.0,
        total_tokens=tokens,
        requests_per_minute=round(rpm, 3),
        by_provider=list(by_provider.values()),
        by_model=list(by_model.values()),
        latency_series=latency_series,
        throughput_series=throughput_series,
        error_series=error_series,
    )