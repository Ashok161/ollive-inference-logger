from __future__ import annotations

import json
from typing import Any, AsyncIterator, Iterator

import httpx

from ..errors import raise_for_provider_response
from ..models import ChatMessage, TokenUsage
from .base import ProviderAdapter


class OpenAICompatAdapter(ProviderAdapter):
    """OpenAI-compatible Chat Completions (Groq, OpenAI, many others)."""

    def __init__(self, name: str, api_key: str, base_url: str) -> None:
        super().__init__(api_key=api_key, base_url=base_url.rstrip("/"))
        self.name = name

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self, model: str, messages: list[ChatMessage], stream: bool, **kwargs: Any
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": stream,
        }
        # Groq/OpenAI support this; omit if caller disables
        if stream and kwargs.pop("include_usage", True):
            payload["stream_options"] = {"include_usage": True}
        for key in ("temperature", "max_tokens", "top_p"):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]
        return payload

    @staticmethod
    def _usage_from(data: dict[str, Any]) -> TokenUsage:
        usage = data.get("usage") or {}
        return TokenUsage(
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
        )

    def chat(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> tuple[str, TokenUsage]:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(model, messages, stream=False, **kwargs),
            )
            raise_for_provider_response(resp, provider=self.name, model=model)
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            return content, self._usage_from(data)

    def chat_stream(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> Iterator[tuple[str, TokenUsage | None]]:
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(model, messages, stream=True, **kwargs),
            ) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    raise_for_provider_response(resp, provider=self.name, model=model)
                usage: TokenUsage | None = None
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    data = json.loads(payload)
                    if data.get("usage"):
                        usage = self._usage_from(data)
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if piece:
                        yield piece, None
                if usage:
                    yield "", usage

    async def achat(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> tuple[str, TokenUsage]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(model, messages, stream=False, **kwargs),
            )
            raise_for_provider_response(resp, provider=self.name, model=model)
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            return content, self._usage_from(data)

    async def achat_stream(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> AsyncIterator[tuple[str, TokenUsage | None]]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(model, messages, stream=True, **kwargs),
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    raise_for_provider_response(resp, provider=self.name, model=model)
                usage: TokenUsage | None = None
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    data = json.loads(payload)
                    if data.get("usage"):
                        usage = self._usage_from(data)
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if piece:
                        yield piece, None
                if usage:
                    yield "", usage