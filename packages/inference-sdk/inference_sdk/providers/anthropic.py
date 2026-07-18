from __future__ import annotations

import json
from typing import Any, AsyncIterator, Iterator

import httpx

from ..errors import raise_for_provider_response
from ..models import ChatMessage, TokenUsage
from .base import ProviderAdapter


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        super().__init__(
            api_key=api_key,
            base_url=(base_url or "https://api.anthropic.com").rstrip("/"),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _payload(
        self, model: str, messages: list[ChatMessage], stream: bool, **kwargs: Any
    ) -> dict[str, Any]:
        system = "\n".join(m.content for m in messages if m.role == "system")
        chat = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload: dict[str, Any] = {
            "model": model,
            "messages": chat,
            "max_tokens": kwargs.get("max_tokens") or 1024,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        if kwargs.get("temperature") is not None:
            payload["temperature"] = kwargs["temperature"]
        return payload

    @staticmethod
    def _usage(data: dict[str, Any]) -> TokenUsage:
        usage = data.get("usage") or {}
        prompt = int(usage.get("input_tokens") or 0)
        completion = int(usage.get("output_tokens") or 0)
        return TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        )

    def chat(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> tuple[str, TokenUsage]:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=self._payload(model, messages, stream=False, **kwargs),
            )
            raise_for_provider_response(resp, provider=self.name, model=model)
            data = resp.json()
            content = "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            )
            return content, self._usage(data)

    def chat_stream(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> Iterator[tuple[str, TokenUsage | None]]:
        usage = TokenUsage()
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=self._payload(model, messages, stream=True, **kwargs),
            ) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    raise_for_provider_response(resp, provider=self.name, model=model)
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = json.loads(line[5:].strip())
                    event_type = data.get("type")
                    if event_type == "content_block_delta":
                        delta = data.get("delta") or {}
                        text = delta.get("text") or ""
                        if text:
                            yield text, None
                    elif event_type == "message_start":
                        msg = data.get("message") or {}
                        usage = self._usage(msg)
                    elif event_type == "message_delta":
                        u = data.get("usage") or {}
                        usage.completion_tokens = int(u.get("output_tokens") or usage.completion_tokens)
                        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
                yield "", usage

    async def achat(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> tuple[str, TokenUsage]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=self._payload(model, messages, stream=False, **kwargs),
            )
            raise_for_provider_response(resp, provider=self.name, model=model)
            data = resp.json()
            content = "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            )
            return content, self._usage(data)

    async def achat_stream(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> AsyncIterator[tuple[str, TokenUsage | None]]:
        usage = TokenUsage()
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=self._payload(model, messages, stream=True, **kwargs),
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    raise_for_provider_response(resp, provider=self.name, model=model)
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = json.loads(line[5:].strip())
                    event_type = data.get("type")
                    if event_type == "content_block_delta":
                        delta = data.get("delta") or {}
                        text = delta.get("text") or ""
                        if text:
                            yield text, None
                    elif event_type == "message_start":
                        msg = data.get("message") or {}
                        usage = self._usage(msg)
                    elif event_type == "message_delta":
                        u = data.get("usage") or {}
                        usage.completion_tokens = int(
                            u.get("output_tokens") or usage.completion_tokens
                        )
                        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
                yield "", usage