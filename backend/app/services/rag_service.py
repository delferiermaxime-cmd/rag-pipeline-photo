# -*- coding: utf-8 -*-
import json
import logging
from typing import AsyncGenerator, Any, Dict, List, Optional

import httpx

from app.config import settings
from app.services.embedding_service import get_embedding
from app.services.qdrant_service import search_chunks

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """Tu réponds uniquement à partir du contexte fourni. Si la réponse n'est pas dans le contexte, dis "Information non trouvée dans les documents fournis."

Sois précis, concis et cite les sources quand c'est pertinent."""


def _build_prompt(question: str, chunks: List[Dict[str, Any]]) -> str:
    parts = []
    for i, c in enumerate(chunks):
        page = c.get("page", "")
        page_str = f" (Page {page})" if page else ""
        parts.append(f"[Source {i+1}: {c.get('title', 'Document')}{page_str}]\n{c.get('content', '')}")
    return f"CONTEXTE:\n{chr(10).join(parts)}\n\nQUESTION: {question}"


async def stream_rag_response(
    question: str,
    user_id: str,
    model: str,
    http_client: httpx.AsyncClient,
    document_ids: Optional[List[str]] = None,
) -> AsyncGenerator[str, None]:
    """Pipeline RAG complet avec streaming SSE."""

    # 1. Embedding de la question
    # FIX : on passe le client partagé — cohérent avec le reste du pipeline
    try:
        query_embedding = await get_embedding(question, http_client)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'error': f'Erreur embedding: {e}'})}\\n\\n"
        return

    # 2. Recherche Qdrant
    try:
        chunks = await search_chunks(
            query_embedding=query_embedding,
            user_id=user_id,
            top_k=settings.TOP_K,
            document_ids=document_ids,
        )
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'error': f'Erreur recherche: {e}'})}\\n\\n"
        return

    # 3. Envoi des sources au frontend
    sources = [
        {
            "document_id": c.get("document_id", ""),
            "title": c.get("title", "Document"),
            "page": c.get("page", ""),
            "content": (c.get("content", "")[:200] + "...") if len(c.get("content", "")) > 200 else c.get("content", ""),
            "score": round(c.get("score", 0.0), 3),
        }
        for c in chunks
    ]
    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\\n\\n"

    if not chunks:
        yield f"data: {json.dumps({'type': 'token', 'token': 'Information non trouvée dans les documents fournis.'})}\\n\\n"
        yield f"data: {json.dumps({'type': 'done'})}\\n\\n"
        return

    # 4. Stream LLM — timeout read=None car la réponse peut être longue
    prompt = _build_prompt(question, chunks)
    stream_timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=5.0)

    try:
        async with http_client.stream(
            "POST",
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": True,
                "options": {"temperature": 0.1, "num_predict": 1024},
            },
            timeout=stream_timeout,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("done"):
                        yield f"data: {json.dumps({'type': 'done'})}\\n\\n"
                        break
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\\n\\n"
                except json.JSONDecodeError:
                    continue
    except httpx.TimeoutException:
        yield f"data: {json.dumps({'type': 'error', 'error': f'Timeout: le modèle {model} met trop de temps à répondre'})}\\n\\n"
    except Exception as e:
        logger.error(f"Erreur streaming LLM: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\\n\\n"


async def list_available_models(http_client: httpx.AsyncClient) -> List[str]:
    """Retourne la liste des modèles Ollama réellement disponibles."""
    try:
        response = await http_client.get(
            f"{settings.OLLAMA_BASE_URL}/api/tags",
            timeout=httpx.Timeout(10.0),
        )
        response.raise_for_status()
        available = [m["name"] for m in response.json().get("models", [])]
        return [
            m for m in settings.OLLAMA_AVAILABLE_MODELS
            if any(m == a or m.split(":")[0] == a.split(":")[0] for a in available)
        ]
    except Exception as e:
        logger.warning(f"Impossible de récupérer les modèles Ollama: {e}")
        return settings.OLLAMA_AVAILABLE_MODELS
