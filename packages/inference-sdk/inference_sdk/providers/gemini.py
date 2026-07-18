from __future__ import annotations

import json
from typing import Any, AsyncIterator, Iterator

import httpx

from ..models import ChatMessage, TokenUsage
from .base import ProviderAdapter


class GeminiAdapter(ProviderAdapter):
    name = "gemini"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        super().__init__(
            api_key=api_key,
            base_url=(base_url or "https://generativelanguage.googleapis.com").rstrip("/"),
        )

    def _url(self, model: str, stream: bool) -> str:
        action = "streamGenerateContent" if stream else "generateContent"
        sep = "&" if stream else "?"
        suffix = f"{sep}alt=sse" if stream else ""
        return (
            f"{self.base_url}/v1beta/models/{model}:{action}"
            f"?key={self.api_key}{suffix}"
        )

    def _payload(self, messages: list[ChatMessage], **kwargs: Any) -> dict[str, Any]:
        contents = []
        system_parts = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                role = "user" if m.role == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m.content}]})
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["system_instruction"] = {
                "parts": [{"text": "\n".join(system_parts)}]
            }
        gen: dict[str, Any] = {}
        if kwargs.get("temperature") is not None:
            gen["temperature"] = kwargs["temperature"]
        if kwargs.get("max_tokens") is not None:
            gen["maxOutputTokens"] = kwargs["max_tokens"]
        if gen:
            payload["generationConfig"] = gen
        return payload

    @staticmethod
    def _parse(data: dict[str, Any]) -> tuple[str, TokenUsage]:
        text = ""
        for cand in data.get("candidates") or []:
            content = cand.get("content") or {}
            for part in content.get("parts") or []:
                text += part.get("text") or ""
        meta = data.get("usageMetadata") or {}
        prompt = int(meta.get("promptTokenCount") or 0)
        completion = int(meta.get("candidatesTokenCount") or 0)
        total = int(meta.get("totalTokenCount") or (prompt + completion))
        return text, TokenUsage(
            prompt_tokens=prompt, completion_tokens=completion, total_tokens=total
        )

    def chat(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> tuple[str, TokenUsage]:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                self._url(model, stream=False),
                json=self._payload(messages, **kwargs),
            )
            resp.raise_for_status()
            return self._parse(resp.json())

    def chat_stream(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> Iterator[tuple[str, TokenUsage | None]]:
        usage = TokenUsage()
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                self._url(model, stream=True),
                json=self._payload(messages, **kwargs),
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = json.loads(line[5:].strip())
                    text, u = self._parse(data)
                    if u.total_tokens:
                        usage = u
                    if text:
                        yield text, None
                yield "", usage

    async def achat(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> tuple[str, TokenUsage]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                self._url(model, stream=False),
                json=self._payload(messages, **kwargs),
            )
            resp.raise_for_status()
            return self._parse(resp.json())

    async def achat_stream(
        self, model: str, messages: list[ChatMessage], **kwargs: Any
    ) -> AsyncIterator[tuple[str, TokenUsage | None]]:
        usage = TokenUsage()
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                self._url(model, stream=True),
                json=self._payload(messages, **kwargs),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = json.loads(line[5:].strip())
                    text, u = self._parse(data)
                    if u.total_tokens:
                        usage = u
                    if text:
                        yield text, None
                yield "", usage