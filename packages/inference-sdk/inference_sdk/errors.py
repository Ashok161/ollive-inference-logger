from __future__ import annotations

import json
from typing import Any

import httpx


class ProviderError(Exception):
    """Normalized provider/API failure with a user-safe message."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        raw: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.provider = provider
        self.model = model
        self.raw = raw

    def __str__(self) -> str:
        prefix = []
        if self.provider:
            prefix.append(self.provider)
        if self.model:
            prefix.append(self.model)
        head = "/".join(prefix)
        if head:
            return f"{head}: {self.message}"
        return self.message


def raise_for_provider_response(
    resp: httpx.Response,
    *,
    provider: str,
    model: str,
) -> None:
    if resp.is_success:
        return
    detail = _extract_detail(resp)
    raise ProviderError(
        detail,
        status_code=resp.status_code,
        provider=provider,
        model=model,
        raw=resp.text[:2000],
    )


def _extract_detail(resp: httpx.Response) -> str:
    text = (resp.text or "").strip()
    if not text:
        return f"HTTP {resp.status_code} {resp.reason_phrase}"
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return text[:500]

    err = data.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("msg") or str(err)
        code = err.get("code") or err.get("type")
        if code:
            return f"{msg} ({code})"
        return str(msg)
    if isinstance(err, str):
        return err
    if "message" in data:
        return str(data["message"])
    return text[:500]