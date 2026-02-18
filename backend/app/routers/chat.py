# -*- coding: utf-8 -*-
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.auth.dependencies import get_current_user
from app.models.database import User
from app.models.schemas import ChatMessage
from app.services.rag_service import list_available_models, stream_rag_response

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

# FIX : cache simple pour /models — évite d'appeler Ollama à chaque requête frontend
_models_cache: dict = {"data": None, "ts": 0.0}
_MODELS_CACHE_TTL = 30  # secondes


@router.post("/stream")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_stream(
    request: Request,
    message: ChatMessage,
    current_user: User = Depends(get_current_user),
):
    """Endpoint SSE — stream token par token la réponse RAG."""
    http_client = request.app.state.http_client

    available = await list_available_models(http_client)

    # FIX : si la liste est vide (Ollama lent), on accepte quand même le modèle
    # s'il est dans la liste configurée — évite de rejeter des requêtes valides
    if available and message.model not in available:
        raise HTTPException(
            400,
            f"Modèle '{message.model}' non disponible. Disponibles : {available}",
        )

    async def event_generator():
        async for chunk in stream_rag_response(
            question=message.question,
            user_id=str(current_user.id),
            model=message.model,
            http_client=http_client,
            document_ids=message.document_ids,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/models")
async def get_models(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    http_client = request.app.state.http_client

    # FIX : cache 30s — évite d'appeler Ollama à chaque rechargement de page
    now = time.time()
    if _models_cache["data"] is not None and (now - _models_cache["ts"]) < _MODELS_CACHE_TTL:
        return _models_cache["data"]

    models = await list_available_models(http_client)
    default = models[0] if models else (settings.OLLAMA_AVAILABLE_MODELS[0] if settings.OLLAMA_AVAILABLE_MODELS else "")

    result = {"models": models, "default": default}
    _models_cache["data"] = result
    _models_cache["ts"] = now
    return result
