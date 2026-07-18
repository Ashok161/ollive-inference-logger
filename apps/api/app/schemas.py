from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TokenUsageIn(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class InferenceLogIn(BaseModel):
    event_id: str
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: str
    provider: str
    model: str
    status: Literal["success", "error", "cancelled"] = "success"
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    latency_ms: float = 0.0
    ttft_ms: Optional[float] = None
    streaming: bool = False
    usage: TokenUsageIn = Field(default_factory=TokenUsageIn)
    input_preview: str = ""
    output_preview: str = ""
    message_count: int = 0
    started_at: datetime
    finished_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    accepted: bool
    event_id: str
    queued: bool = True


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class ConversationOut(BaseModel):
    id: UUID
    title: str
    status: str
    provider: str
    model: str
    session_id: str
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_message(cls, message) -> "MessageOut":
        """Prefer redacted content for public API responses."""
        text = message.content_redacted or message.content
        return cls(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=text,
            status=message.status,
            created_at=message.created_at,
        )


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    provider: Optional[str] = None
    model: Optional[str] = None
    stream: bool = True


class MetricsSummary(BaseModel):
    window_minutes: int
    total_requests: int
    success_count: int
    error_count: int
    cancelled_count: int
    error_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    avg_ttft_ms: float
    total_tokens: int
    requests_per_minute: float
    by_provider: list[dict[str, Any]]
    by_model: list[dict[str, Any]]
    latency_series: list[dict[str, Any]]
    throughput_series: list[dict[str, Any]]
    error_series: list[dict[str, Any]]


class ProviderInfo(BaseModel):
    id: str
    label: str
    models: list[str]
    configured: bool