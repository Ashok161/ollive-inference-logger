from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Iterator

from ..models import ChatMessage, TokenUsage


class ProviderAdapter(ABC):
    name: str

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> tuple[str, TokenUsage]:
        raise NotImplementedError

    @abstractmethod
    def chat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> Iterator[tuple[str, TokenUsage | None]]:
        raise NotImplementedError

    @abstractmethod
    async def achat(
        self,
        model: str,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> tuple[str, TokenUsage]:
        raise NotImplementedError

    @abstractmethod
    async def achat_stream(
        self,
        model: str,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> AsyncIterator[tuple[str, TokenUsage | None]]:
        raise NotImplementedError
        yield  # pragma: no cover