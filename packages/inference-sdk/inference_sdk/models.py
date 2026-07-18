from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Provider(str, Enum):
    GROQ = "groq"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class InferenceLog(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    provider: str
    model: str
    status: Literal["success", "error", "cancelled"] = "success"
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    latency_ms: float = 0.0
    ttft_ms: Optional[float] = None
    streaming: bool = False
    usage: TokenUsage = Field(default_factory=TokenUsage)
    input_preview: str = ""
    output_preview: str = ""
    message_count: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_finished(self) -> None:
        self.finished_at = datetime.now(timezone.utc)