from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis

from ..config import get_settings

logger = logging.getLogger(__name__)


class EventQueue:
    """Redis Streams based event bus for inference logs."""

    def __init__(self) -> None:
        settings = get_settings()
        self.redis_url = settings.redis_url
        self.stream = settings.ingestion_queue
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def publish(self, payload: dict[str, Any]) -> str:
        await self.connect()
        assert self._client is not None
        msg_id = await self._client.xadd(
            self.stream,
            {"payload": json.dumps(payload, default=str)},
            maxlen=100_000,
            approximate=True,
        )
        return msg_id

    async def ensure_group(self, group: str = "workers") -> None:
        await self.connect()
        assert self._client is not None
        try:
            await self._client.xgroup_create(self.stream, group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise


event_queue = EventQueue()