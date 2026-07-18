from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CC_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def redact_pii(text: str, enabled: bool = True) -> str:
    if not enabled or not text:
        return text
    out = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    out = PHONE_RE.sub("[REDACTED_PHONE]", out)
    out = SSN_RE.sub("[REDACTED_SSN]", out)
    out = CC_RE.sub("[REDACTED_CC]", out)
    out = IP_RE.sub("[REDACTED_IP]", out)
    return out


def preview(text: str, limit: int = 240, redact: bool = True) -> str:
    cleaned = redact_pii(text, enabled=redact)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "…"