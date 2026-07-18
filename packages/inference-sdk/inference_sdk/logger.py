from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

import httpx

from .models import InferenceLog

logger = logging.getLogger("inference_sdk")


class LogShipper:
    """Fire-and-forget near-real-time log shipper."""

    def __init__(
        self,
        ingestion_url: str,
        api_key: Optional[str] = None,
        timeout: float = 3.0,
        enabled: bool = True,
    ) -> None:
        self.ingestion_url = ingestion_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.enabled = enabled
        self._client = httpx.Client(timeout=timeout)
        self._async_client: Optional[httpx.AsyncClient] = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Ingest-Key"] = self.api_key
        return headers

    def ship(self, log: InferenceLog) -> None:
        if not self.enabled:
            return

        def _send() -> None:
            try:
                resp = self._client.post(
                    self.ingestion_url,
                    json=log.model_dump(mode="json"),
                    headers=self._headers(),
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Ingest rejected log %s: HTTP %s %s",
                        log.event_id,
                        resp.status_code,
                        resp.text[:200],
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to ship inference log: %s", exc)

        threading.Thread(target=_send, daemon=True).start()

    async def aship(self, log: InferenceLog) -> None:
        if not self.enabled:
            return
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        try:
            resp = await self._async_client.post(
                self.ingestion_url,
                json=log.model_dump(mode="json"),
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                logger.warning(
                    "Ingest rejected log %s: HTTP %s %s",
                    log.event_id,
                    resp.status_code,
                    resp.text[:200],
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to ship inference log: %s", exc)

    def close(self) -> None:
        self._client.close()
        if self._async_client is not None:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._async_client.aclose())
                else:
                    loop.run_until_complete(self._async_client.aclose())
            except Exception:  # noqa: BLE001
                pass