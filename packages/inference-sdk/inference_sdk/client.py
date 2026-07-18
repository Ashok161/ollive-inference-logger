from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Iterator, Optional
from uuid import uuid4

from .logger import LogShipper
from .models import ChatMessage, InferenceLog, Provider, TokenUsage
from .pii import preview
from .providers import get_adapter


class InstrumentedLLM:
    """
    Auto-instrumenting multi-provider LLM client.

    Every chat/stream call captures inference metadata and ships it
    near-real-time to the configured ingestion endpoint.
    """

    def __init__(
        self,
        provider: str | Provider = "groq",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        ingestion_url: Optional[str] = None,
        ingestion_api_key: Optional[str] = None,
        redact_pii: bool = True,
        enabled: bool = True,
    ) -> None:
        self.provider = Provider(provider) if isinstance(provider, str) else provider
        self.model = model or os.getenv("DEFAULT_MODEL", "llama-3.3-70b-versatile")
        self.adapter = get_adapter(self.provider, api_key=api_key, base_url=base_url)
        self.redact_pii = redact_pii
        self.shipper = LogShipper(
            ingestion_url=ingestion_url
            or os.getenv("INGESTION_URL", "http://localhost:8000/v1/ingest"),
            api_key=ingestion_api_key or os.getenv("INGESTION_API_KEY"),
            enabled=enabled,
        )

    def _build_log(
        self,
        messages: list[ChatMessage],
        *,
        conversation_id: Optional[str],
        session_id: Optional[str],
        streaming: bool,
        metadata: Optional[dict[str, Any]],
    ) -> InferenceLog:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return InferenceLog(
            conversation_id=conversation_id,
            session_id=session_id or str(uuid4()),
            provider=self.provider.value,
            model=self.model,
            streaming=streaming,
            input_preview=preview(last_user, redact=self.redact_pii),
            message_count=len(messages),
            started_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )

    def chat(
        self,
        messages: list[ChatMessage] | list[dict[str, str]],
        *,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        msgs = [
            m if isinstance(m, ChatMessage) else ChatMessage(**m) for m in messages
        ]
        log = self._build_log(
            msgs,
            conversation_id=conversation_id,
            session_id=session_id,
            streaming=False,
            metadata=metadata,
        )
        started = time.perf_counter()
        try:
            content, usage = self.adapter.chat(self.model, msgs, **kwargs)
            log.usage = usage
            log.output_preview = preview(content, redact=self.redact_pii)
            log.status = "success"
            return content
        except Exception as exc:  # noqa: BLE001
            log.status = "error"
            log.error_type = type(exc).__name__
            log.error_message = str(exc)[:500]
            raise
        finally:
            log.latency_ms = (time.perf_counter() - started) * 1000
            log.mark_finished()
            self.shipper.ship(log)

    def chat_stream(
        self,
        messages: list[ChatMessage] | list[dict[str, str]],
        *,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        msgs = [
            m if isinstance(m, ChatMessage) else ChatMessage(**m) for m in messages
        ]
        log = self._build_log(
            msgs,
            conversation_id=conversation_id,
            session_id=session_id,
            streaming=True,
            metadata=metadata,
        )
        started = time.perf_counter()
        first_token_at: float | None = None
        chunks: list[str] = []
        usage = TokenUsage()
        try:
            for piece, maybe_usage in self.adapter.chat_stream(self.model, msgs, **kwargs):
                if cancel_check and cancel_check():
                    log.status = "cancelled"
                    break
                if maybe_usage is not None:
                    usage = maybe_usage
                    continue
                if piece:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                        log.ttft_ms = (first_token_at - started) * 1000
                    chunks.append(piece)
                    yield piece
            else:
                log.status = "success"
            content = "".join(chunks)
            log.usage = usage
            log.output_preview = preview(content, redact=self.redact_pii)
        except Exception as exc:  # noqa: BLE001
            log.status = "error"
            log.error_type = type(exc).__name__
            log.error_message = str(exc)[:500]
            raise
        finally:
            log.latency_ms = (time.perf_counter() - started) * 1000
            log.mark_finished()
            self.shipper.ship(log)

    async def achat(
        self,
        messages: list[ChatMessage] | list[dict[str, str]],
        *,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        msgs = [
            m if isinstance(m, ChatMessage) else ChatMessage(**m) for m in messages
        ]
        log = self._build_log(
            msgs,
            conversation_id=conversation_id,
            session_id=session_id,
            streaming=False,
            metadata=metadata,
        )
        started = time.perf_counter()
        try:
            content, usage = await self.adapter.achat(self.model, msgs, **kwargs)
            log.usage = usage
            log.output_preview = preview(content, redact=self.redact_pii)
            log.status = "success"
            return content
        except Exception as exc:  # noqa: BLE001
            log.status = "error"
            log.error_type = type(exc).__name__
            log.error_message = str(exc)[:500]
            raise
        finally:
            log.latency_ms = (time.perf_counter() - started) * 1000
            log.mark_finished()
            await self.shipper.aship(log)

    async def achat_stream(
        self,
        messages: list[ChatMessage] | list[dict[str, str]],
        *,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        msgs = [
            m if isinstance(m, ChatMessage) else ChatMessage(**m) for m in messages
        ]
        log = self._build_log(
            msgs,
            conversation_id=conversation_id,
            session_id=session_id,
            streaming=True,
            metadata=metadata,
        )
        started = time.perf_counter()
        first_token_at: float | None = None
        chunks: list[str] = []
        usage = TokenUsage()
        cancelled = False
        try:
            async for piece, maybe_usage in self.adapter.achat_stream(
                self.model, msgs, **kwargs
            ):
                if cancel_check and cancel_check():
                    cancelled = True
                    log.status = "cancelled"
                    break
                if maybe_usage is not None:
                    usage = maybe_usage
                    continue
                if piece:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                        log.ttft_ms = (first_token_at - started) * 1000
                    chunks.append(piece)
                    yield piece
            if not cancelled:
                log.status = "success"
            content = "".join(chunks)
            log.usage = usage
            log.output_preview = preview(content, redact=self.redact_pii)
        except Exception as exc:  # noqa: BLE001
            log.status = "error"
            log.error_type = type(exc).__name__
            log.error_message = str(exc)[:500]
            raise
        finally:
            log.latency_ms = (time.perf_counter() - started) * 1000
            log.mark_finished()
            await self.shipper.aship(log)