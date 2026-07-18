from __future__ import annotations

import os
from typing import Optional

from ..models import Provider
from .anthropic import AnthropicAdapter
from .base import ProviderAdapter
from .gemini import GeminiAdapter
from .openai_compat import OpenAICompatAdapter

DEFAULT_BASE_URLS = {
    Provider.GROQ: "https://api.groq.com/openai/v1",
    Provider.OPENAI: "https://api.openai.com/v1",
}


def get_adapter(
    provider: str | Provider,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> ProviderAdapter:
    p = Provider(provider) if isinstance(provider, str) else provider

    if p == Provider.GROQ:
        key = api_key or os.getenv("GROQ_API_KEY", "")
        if not key:
            raise ValueError("GROQ_API_KEY is required for provider=groq")
        return OpenAICompatAdapter(
            name="groq",
            api_key=key,
            base_url=base_url or DEFAULT_BASE_URLS[Provider.GROQ],
        )

    if p == Provider.OPENAI:
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY is required for provider=openai")
        return OpenAICompatAdapter(
            name="openai",
            api_key=key,
            base_url=base_url or DEFAULT_BASE_URLS[Provider.OPENAI],
        )

    if p == Provider.ANTHROPIC:
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is required for provider=anthropic")
        return AnthropicAdapter(api_key=key, base_url=base_url)

    if p == Provider.GEMINI:
        key = api_key or os.getenv("GOOGLE_API_KEY", "")
        if not key:
            raise ValueError("GOOGLE_API_KEY is required for provider=gemini")
        return GeminiAdapter(api_key=key, base_url=base_url)

    raise ValueError(f"Unsupported provider: {provider}")