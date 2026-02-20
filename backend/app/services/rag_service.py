# -*- coding: utf-8 -*-
import base64
import json
import logging
import os
import time
from typing import AsyncGenerator, Any, Dict, List, Optional

import httpx

from app.config import settings
from app.services.embedding_service import get_embedding
from app.services.qdrant_service import search_chunks
from app.services.docling_service import IMAGES_DIR

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """Tu es un assistant RAG.

Tu dois répondre prioritairement à partir du CONTEXTE fourni.
N’utilise tes connaissances générales que si le contexte est totalement insuffisant.

RÈGLES :

1. Lis l’intégralité du contexte.
2. Si l'utilisateur demande :
   - "mot pour mot", "textuellement", "copie exacte" :
     → Reproduis exactement le passage concerné sans modification.
3. Si la question demande :
   - une liste,
   - un ensemble d’éléments,
   - une synthèse multi-sources,
   → Agrège toutes les informations pertinentes présentes dans le contexte.
4. Si plusieurs sources contiennent des éléments complémentaires,
   tu dois les combiner pour produire une réponse complète.
5. Si l’information est partielle, fournis tout ce qui est disponible dans le contexte.
6. Ne réponds "Information non trouvée dans le contexte" que si
   aucune information pertinente n’apparaît dans aucun extrait.
7. Cite les sources sous la forme : (Titre, p.X)
8. Réponds toujours en français."""

_MIN_RELEVANT_SCORE = 0.45

_vision_cache: Dict[str, Dict] = {}
_VISION_CACHE_TTL = 300


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


def _load_image_base64(filename: str) -> Optional[str]:
    filepath = os.path.join(IMAGES_DIR, filename)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.warning(f"Impossible de charger l'image {filename}: {e}")
        return None


async def _check_vision_support(model: str, http_client: httpx.AsyncClient) -> bool:
    now = time.time()
    cached = _vision_cache.get(model)
    if cached and (now - cached["ts"]) < _VISION_CACHE_TTL:
        return cached["supports"]

    try:
        response = await http_client.post(
            f"{settings.OLLAMA_BASE_URL}/api/show",
            json={"name": model},
            timeout=httpx.Timeout(10.0),
        )
        if response.status_code != 200:
            _vision_cache[model] = {"supports": False, "ts": now}
            return False
        data = response.json()
        model_info = str(data).lower()
        supports = "clip" in model_info or "vision" in model_info or "multimodal" in model_info
        _vision_cache[model] = {"supports": supports, "ts": now}
        logger.info(f"Vision cache mis à jour — {model}: {supports}")
        return supports
    except Exception as e:
        logger.debug(f"Impossible de vérifier la vision pour {model}: {e}")
        return False


async def _condense_question(
    question: str,
    history: List[Dict],
    http_client: httpx.AsyncClient,
    model: str,
) -> str:
    if not history:
        return question

    ref_indicators = ["et ", "aussi", "le suivant", "précédent", "celui", "celle",
                      "ce point", "ça", "cela", "il ", "elle ", "ils ", "elles ",
                      "même", "encore", "suite", "après", "avant", "pareil"]
    question_lower = question.lower()
    needs_condensation = len(question) < 80 or any(ind in question_lower for ind in ref_indicators)

    if not needs_condensation:
        return question

    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:200]}"
        for m in history[-6:]
    )
    condensation_prompt = f"""Voici l'historique d'une conversation :
{history_text}

Nouvelle question de l'utilisateur : "{question}"

Reformule cette question en une question AUTONOME et COMPLÈTE qui peut être comprise sans l'historique.
Si la question est déjà autonome, retourne-la telle quelle.
Réponds UNIQUEMENT avec la question reformulée, sans explication."""

    try:
        response = await http_client.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": condensation_prompt}],
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 150},
            },
            timeout=httpx.Timeout(20.0),
        )
        response.raise_for_status()
        condensed = response.json().get("message", {}).get("content", "").strip()
        if condensed and len(condensed) > 5:
            logger.info(f"Question condensée : '{question}' → '{condensed}'")
            return condensed
    except Exception as e:
        logger.warning(f"Condensation échouée, question originale utilisée : {e}")

    return question


async def stream_rag_response(
    question: str,
    user_id: str,
    model: str,
    http_client: httpx.AsyncClient,
    document_ids: Optional[List[str]] = None,
    history: Optional[List[Dict]] = None,
    temperature: Optional[float] = 0.1,
    top_k: Optional[int] = None,  # None = utilise settings.TOP_K (défaut 8)
    max_tokens: Optional[int] = 1024,
    min_score: Optional[float] = 0.3,
    context_max_chars: Optional[int] = 12000,
    system_prompt: Optional[str] = None,
    skip_rag: bool = False,  # NOUVEAU : si True, bypass total de Qdrant
) -> AsyncGenerator[str, None]:

    # Mode sans RAG — on envoie directement la question au LLM sans chercher dans Qdrant
    if skip_rag:
        yield _sse({"type": "sources", "sources": []})
        prompt = question
        effective_prompt = system_prompt if system_prompt and system_prompt.strip() else RAG_SYSTEM_PROMPT
        messages = [{"role": "system", "content": effective_prompt}]
        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})

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
            logger.error(f"Erreur streaming LLM (skip_rag): {e}")
            yield _sse({"type": "error", "error": str(e)})
        return

    # Mode normal avec RAG
    # 1. Condensation de la question si nécessaire
    search_question = question
    if history:
        try:
            search_question = await _condense_question(question, history, http_client, model)
        except Exception as e:
            logger.warning(f"Condensation ignorée : {e}")

    # 2. Embedding
    try:
        query_embedding = await get_embedding(search_question, http_client)
    except Exception as e:
        yield _sse({"type": "error", "error": f"Erreur embedding: {e}"})
        return

    # 3. Recherche Qdrant
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

    # 4. Sources
    sources = [
        {
            "document_id": c.get("document_id", ""),
            "title": c.get("title", "Document"),
            "page": c.get("page", ""),
            "content": c.get("content", ""),  # chunk complet envoyé au frontend
            "score": round(c.get("score", 0.0), 3),
            "image_filenames": c.get("image_filenames", []),
        }
        for c in chunks
    ]
    yield _sse({"type": "sources", "sources": sources})

    # 5. Vision
    supports_vision = await _check_vision_support(model, http_client)

    # 6. Prompt
    relevant_chunks = [c for c in chunks if c.get("score", 0) >= _MIN_RELEVANT_SCORE]

    if relevant_chunks:
        prompt = _build_prompt(
            question,
            relevant_chunks,
            context_max_chars=context_max_chars if context_max_chars else 12000
        )
    elif chunks:
        prompt = (
            f"Les documents disponibles ne contiennent pas d'information pertinente "
            f"pour cette question. Réponds depuis tes connaissances générales.\n\n"
            f"QUESTION : {question}"
        )
    else:
        prompt = f"Aucun document n'est disponible. Réponds depuis tes connaissances générales.\n\nQUESTION : {question}"

    # 7. Messages
    effective_prompt = system_prompt if system_prompt and system_prompt.strip() else RAG_SYSTEM_PROMPT
    messages = [{"role": "system", "content": effective_prompt}]
    if history:
        for msg in history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    # 8. Images si vision supportée
    if supports_vision and relevant_chunks:
        image_filenames = []
        seen = set()
        for c in relevant_chunks[:3]:
            for fname in c.get("image_filenames", []):
                if fname not in seen:
                    image_filenames.append(fname)
                    seen.add(fname)

        if image_filenames:
            user_content = [{"type": "text", "text": prompt}]
            for fname in image_filenames[:3]:
                b64 = _load_image_base64(fname)
                if b64:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}
                    })
            messages.append({"role": "user", "content": user_content})
            logger.info(f"Vision : {len([c for c in user_content if c['type'] == 'image_url'])} images envoyées")
        else:
            messages.append({"role": "user", "content": prompt})
    else:
        messages.append({"role": "user", "content": prompt})

    # 9. Stream LLM
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
        response = await http_client.get(
            f"{settings.OLLAMA_BASE_URL}/api/tags",
            timeout=httpx.Timeout(10.0)
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
