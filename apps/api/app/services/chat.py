from __future__ import annotations

import os
from typing import AsyncIterator
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from inference_sdk import ChatMessage, InstrumentedLLM

from ..config import get_settings
from ..models import Conversation, Message
from .pii import redact_pii


PROVIDERS = {
    "groq": {
        "label": "Groq",
        # mixtral-8x7b-32768 was decommissioned (returns HTTP 400).
        "models": [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
        ],
        "env": "GROQ_API_KEY",
    },
    "openai": {
        "label": "OpenAI",
        "models": ["gpt-4.1", "gpt-4o", "gpt-4o-mini"],
        "env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "label": "Anthropic",
        "models": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-latest"],
        "env": "ANTHROPIC_API_KEY",
    },
    "gemini": {
        "label": "Google Gemini",
        "models": ["gemini-2.0-flash", "gemini-1.5-flash"],
        "env": "GOOGLE_API_KEY",
    },
}


def list_providers() -> list[dict]:
    settings = get_settings()
    env_map = {
        "GROQ_API_KEY": settings.groq_api_key,
        "OPENAI_API_KEY": settings.openai_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "GOOGLE_API_KEY": settings.google_api_key,
    }
    out = []
    for pid, meta in PROVIDERS.items():
        configured = bool(env_map.get(meta["env"]) or os.getenv(meta["env"]))
        out.append(
            {
                "id": pid,
                "label": meta["label"],
                "models": meta["models"],
                "configured": configured,
            }
        )
    return out


def build_llm(provider: str, model: str) -> InstrumentedLLM:
    settings = get_settings()
    os.environ.setdefault("GROQ_API_KEY", settings.groq_api_key)
    os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    return InstrumentedLLM(
        provider=provider,
        model=model,
        ingestion_url=settings.ingestion_url,
        ingestion_api_key=settings.ingestion_api_key,
        redact_pii=settings.pii_redaction_enabled,
    )


async def create_conversation(
    session: AsyncSession,
    *,
    title: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> Conversation:
    settings = get_settings()
    conv = Conversation(
        title=title or "New conversation",
        provider=provider or settings.default_provider,
        model=model or settings.default_model,
        session_id=str(uuid4()),
        status="active",
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def list_conversations(session: AsyncSession) -> list[tuple[Conversation, int]]:
    msg_count = (
        select(Message.conversation_id, func.count(Message.id).label("cnt"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    stmt = (
        select(Conversation, func.coalesce(msg_count.c.cnt, 0))
        .outerjoin(msg_count, Conversation.id == msg_count.c.conversation_id)
        .order_by(Conversation.updated_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], int(row[1])) for row in rows]


async def get_conversation(session: AsyncSession, conversation_id: UUID) -> Conversation | None:
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    return await session.scalar(stmt)


async def cancel_conversation(session: AsyncSession, conversation_id: UUID) -> Conversation | None:
    conv = await get_conversation(session, conversation_id)
    if not conv:
        return None
    conv.cancel_requested = True
    conv.status = "cancelled"
    await session.commit()
    await session.refresh(conv)
    return conv


async def resume_conversation(session: AsyncSession, conversation_id: UUID) -> Conversation | None:
    conv = await get_conversation(session, conversation_id)
    if not conv:
        return None
    conv.cancel_requested = False
    conv.status = "active"
    await session.commit()
    await session.refresh(conv)
    return conv


def _context_messages(conv: Conversation, limit: int) -> list[ChatMessage]:
    history = [
        ChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
        for m in conv.messages
        if m.role in ("system", "user", "assistant") and m.status != "cancelled"
    ]
    system = ChatMessage(
        role="system",
        content=(
            "You are a helpful assistant for the Ollive inference logging demo. "
            "Keep answers concise and useful."
        ),
    )
    recent = history[-limit:]
    return [system, *recent]


async def stream_chat(
    session: AsyncSession,
    conversation_id: UUID,
    user_text: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    settings = get_settings()
    conv = await get_conversation(session, conversation_id)
    if not conv:
        raise ValueError("Conversation not found")
    if conv.status == "cancelled" and conv.cancel_requested:
        # allow resume path to clear this first
        raise ValueError("Conversation is cancelled. Resume it to continue.")

    if provider:
        conv.provider = provider
    if model:
        conv.model = model

    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=user_text,
        content_redacted=redact_pii(user_text, settings.pii_redaction_enabled),
        status="completed",
    )
    session.add(user_msg)
    await session.commit()

    # refresh with messages
    conv = await get_conversation(session, conversation_id)
    assert conv is not None

    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content="",
        status="streaming",
    )
    session.add(assistant)
    await session.commit()
    await session.refresh(assistant)

    llm = build_llm(conv.provider, conv.model)
    messages = _context_messages(conv, settings.context_window_messages)
    # include the just-added user message if not yet in relationship
    if not messages or messages[-1].content != user_text:
        messages.append(ChatMessage(role="user", content=user_text))

    chunks: list[str] = []
    cancel_state = {"requested": False}

    async def refresh_cancel() -> bool:
        await session.refresh(conv)
        cancel_state["requested"] = bool(conv.cancel_requested)
        return cancel_state["requested"]

    def cancel_check() -> bool:
        return cancel_state["requested"]

    was_cancelled = False
    try:
        async for piece in llm.achat_stream(
            messages,
            conversation_id=str(conv.id),
            session_id=conv.session_id,
            cancel_check=cancel_check,
            metadata={"source": "chatbot"},
        ):
            chunks.append(piece)
            assistant.content = "".join(chunks)
            yield piece

            if await refresh_cancel():
                was_cancelled = True
                assistant.status = "cancelled"
                conv.status = "cancelled"
                await session.commit()
                break

        if was_cancelled or await refresh_cancel():
            was_cancelled = True
            assistant.content = "".join(chunks)
            assistant.content_redacted = redact_pii(
                assistant.content, settings.pii_redaction_enabled
            )
            assistant.status = "cancelled"
            conv.status = "cancelled"
        else:
            assistant.content = "".join(chunks)
            assistant.content_redacted = redact_pii(
                assistant.content, settings.pii_redaction_enabled
            )
            assistant.status = "completed"
            if not conv.title or conv.title == "New conversation":
                conv.title = user_text[:60] + ("…" if len(user_text) > 60 else "")
            conv.status = "active"
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        message = str(exc).strip() or "Model request failed"
        if message.startswith("Error:"):
            message = message[6:].strip()
        assistant.content = "".join(chunks) or message
        assistant.status = "error"
        await session.commit()
        raise ValueError(message) from exc
    finally:
        await session.refresh(assistant)
        if assistant.status == "streaming":
            assistant.status = "cancelled"
            conv.status = "cancelled"
            assistant.content = "".join(chunks)
            await session.commit()