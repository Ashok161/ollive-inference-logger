from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_db
from ..schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    MessageOut,
)
from ..services import chat as chat_service

router = APIRouter(prefix="/v1", tags=["conversations"])


def _conv_out(conv, message_count: int = 0) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        status=conv.status,
        provider=conv.provider,
        model=conv.model,
        session_id=conv.session_id,
        cancel_requested=conv.cancel_requested,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=message_count,
    )


@router.get("/providers")
async def providers():
    return chat_service.list_providers()


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    body: ConversationCreate,
    session: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    conv = await chat_service.create_conversation(
        session,
        title=body.title,
        provider=body.provider or settings.default_provider,
        model=body.model or settings.default_model,
    )
    return _conv_out(conv, 0)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(session: AsyncSession = Depends(get_db)):
    rows = await chat_service.list_conversations(session)
    return [_conv_out(c, n) for c, n in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: UUID, session: AsyncSession = Depends(get_db)):
    conv = await chat_service.get_conversation(session, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetail(
        **_conv_out(conv, len(conv.messages)).model_dump(),
        messages=[MessageOut.model_validate(m) for m in conv.messages],
    )


@router.post("/conversations/{conversation_id}/cancel", response_model=ConversationOut)
async def cancel_conversation(conversation_id: UUID, session: AsyncSession = Depends(get_db)):
    conv = await chat_service.cancel_conversation(session, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_out(conv, len(conv.messages))


@router.post("/conversations/{conversation_id}/resume", response_model=ConversationOut)
async def resume_conversation(conversation_id: UUID, session: AsyncSession = Depends(get_db)):
    conv = await chat_service.resume_conversation(session, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_out(conv, len(conv.messages))


@router.post("/conversations/{conversation_id}/chat")
async def chat(
    conversation_id: UUID,
    body: ChatRequest,
    session: AsyncSession = Depends(get_db),
):
    conv = await chat_service.get_conversation(session, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not body.stream:
        chunks: list[str] = []
        try:
            async for piece in chat_service.stream_chat(
                session,
                conversation_id,
                body.message,
                provider=body.provider,
                model=body.model,
            ):
                chunks.append(piece)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        updated = await chat_service.get_conversation(session, conversation_id)
        return {
            "conversation_id": str(conversation_id),
            "content": "".join(chunks),
            "conversation": _conv_out(updated, len(updated.messages) if updated else 0),
        }

    async def event_gen():
        try:
            async for piece in chat_service.stream_chat(
                session,
                conversation_id,
                body.message,
                provider=body.provider,
                model=body.model,
            ):
                if piece:
                    yield f"data: {json.dumps({'type': 'token', 'content': piece})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except ValueError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")