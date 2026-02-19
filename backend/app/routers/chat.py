# -*- coding: utf-8 -*-
import json
import logging
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.auth.dependencies import get_current_user
from app.models.database import AsyncSessionLocal, ChatMessage, Conversation, User, get_db
from app.models.schemas import ChatMessageRequest, ConversationDetail, ConversationOut
from app.services.rag_service import list_available_models, stream_rag_response

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

# FIX cache modèles : structure avec timestamp pour invalidation
_models_cache: dict = {"data": None, "ts": 0.0}
_MODELS_CACHE_TTL = 30  # secondes


async def _get_available_models(http_client) -> list:
    """
    FIX : si la liste retournée est vide (Ollama redémarré, modèles rechargés),
    on invalide le cache immédiatement au lieu d'attendre le TTL.
    Évite de retourner des modèles qui n'existent plus après un redémarrage Ollama.
    """
    now = time.time()
    cached = _models_cache["data"]
    cache_valid = cached is not None and (now - _models_cache["ts"]) < _MODELS_CACHE_TTL

    if cache_valid:
        return cached

    models = await list_available_models(http_client)

    # FIX : on ne met en cache que si la liste n'est pas vide
    # Si Ollama vient de redémarrer et n'a pas encore ses modèles, on ne cache pas
    if models:
        _models_cache["data"] = models
        _models_cache["ts"] = now
    else:
        # Invalidation du cache — forcera un nouveau fetch au prochain appel
        _models_cache["data"] = None
        _models_cache["ts"] = 0.0

    return models


@router.post("/stream")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_stream(
    request: Request,
    message: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
):
    http_client = request.app.state.http_client
    available = await _get_available_models(http_client)
    if available and message.model not in available:
        raise HTTPException(400, f"Modèle '{message.model}' non disponible. Disponibles : {available}")

    history = []
    conversation_id = message.conversation_id

    async with AsyncSessionLocal() as db:
        if conversation_id:
            conv = await db.get(Conversation, UUID(conversation_id))
            if not conv or str(conv.user_id) != str(current_user.id):
                raise HTTPException(404, "Conversation introuvable")
            result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == UUID(conversation_id))
                .order_by(ChatMessage.created_at)
            )
            msgs = result.scalars().all()
            history = [{"role": m.role, "content": m.content} for m in msgs]
        else:
            title = message.question[:60] + ("…" if len(message.question) > 60 else "")
            conv = Conversation(user_id=current_user.id, title=title)
            db.add(conv)
            await db.flush()
            await db.refresh(conv)
            conversation_id = str(conv.id)

        user_msg = ChatMessage(
            conversation_id=UUID(conversation_id),
            role="user",
            content=message.question
        )
        db.add(user_msg)
        await db.commit()

    full_response = []

    async def event_generator():
        yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conversation_id})}\n\n"

        async for chunk in stream_rag_response(
            question=message.question,
            user_id=str(current_user.id),
            model=message.model,
            http_client=http_client,
            document_ids=message.document_ids,
            history=history,
            temperature=message.temperature,
            top_k=message.top_k,
            max_tokens=message.max_tokens,
            min_score=message.min_score,
            context_max_chars=message.context_max_chars,
            system_prompt=message.system_prompt,
            skip_rag=message.skip_rag,
        ):
            try:
                data = json.loads(chunk.removeprefix("data: ").strip())
                if data.get("type") == "token":
                    full_response.append(data.get("token", ""))
                elif data.get("type") == "done" and full_response:
                    async with AsyncSessionLocal() as db:
                        assistant_msg = ChatMessage(
                            conversation_id=UUID(conversation_id),
                            role="assistant",
                            content="".join(full_response),
                        )
                        db.add(assistant_msg)
                        await db.commit()
            except Exception:
                pass
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    conv = await db.get(Conversation, UUID(conversation_id))
    if not conv or str(conv.user_id) != str(current_user.id):
        raise HTTPException(404, "Conversation introuvable")
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == UUID(conversation_id))
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "messages": messages,
    }


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    conv = await db.get(Conversation, UUID(conversation_id))
    if not conv or str(conv.user_id) != str(current_user.id):
        raise HTTPException(404, "Conversation introuvable")
    await db.delete(conv)
    await db.commit()


@router.get("/models")
async def get_models(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    http_client = request.app.state.http_client
    models = await _get_available_models(http_client)
    default = models[0] if models else (
        settings.OLLAMA_AVAILABLE_MODELS[0] if settings.OLLAMA_AVAILABLE_MODELS else ""
    )
    return {"models": models, "default": default}
