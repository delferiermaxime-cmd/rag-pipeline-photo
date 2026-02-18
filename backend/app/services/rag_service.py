# -*- coding: utf-8 -*-
import json
import logging
from typing import AsyncGenerator, Any, Dict, List, Optional

import httpx

from app.config import settings
from app.services.embedding_service import get_embedding
from app.services.qdrant_service import search_chunks

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """Tu es un assistant intelligent. Tu as accès à des documents fournis dans le contexte.

Règles :
1. Si la réponse est dans les documents fournis, réponds en te basant sur eux et cite les sources.
2. Si la réponse n'est pas dans les documents mais que tu la connais, réponds normalement en précisant que l'information vient de tes connaissances générales et non des documents.
3. Sois précis et concis."""


def _sse(data: dict) -> str:
    return "data: " + json.dumps(data) + "\n\n"


def _build_prompt(question: str, chunks: List[Dict[str, Any]], context_max_chars: int = 12000) -> str:
    parts = []
    total_chars = 0
    for i, c in enumerate(chunks):
        page = c.get("page", "")
        page_str = f" (Page {page})" if page else ""
        chunk_text = f"[Source {i+1}: {c.get('title', 'Document')}{page_str}]\n{c.get('content', '')}"
        if total_chars + len(chunk_text) > context_max_chars:
            break
        parts.append(chunk_text)
        total_chars += len(chunk_text)
    return f"CONTEXTE:\n{chr(10).join(parts)}\n\nQUESTION: {question}"


async def stream_rag_response(
    question: str,
    user_id: str,
    model: str,
    http_client: httpx.AsyncClient,
    document_ids: Optional[List[str]] = None,
    history: Optional[List[Dict]] = None,
    temperature: Optional[float] = 0.1,
    top_k: Optional[int] = None,
    max_tokens: Optional[int] = 1024,
    min_score: Optional[float] = 0.3,
    context_max_chars: Optional[int] = 12000,
) -> AsyncGenerator[str, None]:

    # 1. Embedding
    try:
        query_embedding = await get_embedding(question, http_client)
    except Exception as e:
        yield _sse({"type": "error", "error": f"Erreur embedding: {e}"})
        return

    # 2. Recherche Qdrant avec top_k depuis settings ou paramètre
    effective_top_k = top_k if top_k is not None else settings.TOP_K
    try:
        chunks = await search_chunks(
            query_embedding=query_embedding,
            user_id=user_id,
            top_k=effective_top_k,
            document_ids=document_ids,
            min_score=min_score if min_score is not None else 0.0,
        )
    except Exception as e:
        yield _sse({"type": "error", "error": f"Erreur recherche: {e}"})
        return

    # 3. Sources
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
    yield _sse({"type": "sources", "sources": sources})

    if not chunks:
        yield _sse({"type": "token", "token": "Information non trouvée dans les documents fournis."})
        yield _sse({"type": "done"})
        return

    # 4. Construction messages avec historique
    prompt = _build_prompt(question, chunks, context_max_chars=context_max_chars if context_max_chars else 12000)
    messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    if history:
        for msg in history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})

    # 5. Stream LLM avec paramètres utilisateur
    logger.info(f"RAG: {len(chunks)} chunks, min_score={min_score}, context_max={context_max_chars}")
    stream_timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=5.0)
    try:
        async with http_client.stream(
            "POST",
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": temperature if temperature is not None else 0.1,
                    "num_predict": max_tokens if max_tokens is not None else 1024,
                },
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
                        yield _sse({"type": "done"})
                        break
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield _sse({"type": "token", "token": token})
                except json.JSONDecodeError:
                    continue
    except httpx.TimeoutException:
        yield _sse({"type": "error", "error": f"Timeout: le modèle {model} met trop de temps à répondre"})
    except Exception as e:
        logger.error(f"Erreur streaming LLM: {e}")
        yield _sse({"type": "error", "error": str(e)})


async def list_available_models(http_client: httpx.AsyncClient) -> List[str]:
    try:
        response = await http_client.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=httpx.Timeout(10.0))
        response.raise_for_status()
        available = [m["name"] for m in response.json().get("models", [])]
        return [m for m in settings.OLLAMA_AVAILABLE_MODELS
                if any(m == a or m.split(":")[0] == a.split(":")[0] for a in available)]
    except Exception as e:
        logger.warning(f"Impossible de récupérer les modèles Ollama: {e}")
        return settings.OLLAMA_AVAILABLE_MODELS
