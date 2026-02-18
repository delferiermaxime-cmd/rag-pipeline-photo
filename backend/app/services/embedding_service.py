# -*- coding: utf-8 -*-
import logging
from typing import List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def get_embedding(text: str) -> List[float]:
    embeddings = await get_embeddings([text])
    return embeddings[0]


async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Obtient les embeddings pour une liste de textes via Ollama."""
    results = []
    async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
        for text in texts:
            response = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": settings.OLLAMA_EMBEDDING_MODEL, "prompt": text},
            )
            response.raise_for_status()
            embedding = response.json().get("embedding", [])
            if not embedding:
                raise ValueError(f"Embedding vide retourné pour : {text[:50]}")
            results.append(embedding)
    return results


async def verify_embedding_model() -> int:
    """Vérifie le modèle d'embedding et retourne sa dimension."""
    embedding = await get_embedding("test de dimension")
    dim = len(embedding)
    if dim == 0:
        raise ValueError("Le modèle d'embedding retourne des vecteurs vides")
    logger.info(f"Modèle d'embedding OK : {settings.OLLAMA_EMBEDDING_MODEL}, dim={dim}")
    return dim
