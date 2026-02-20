# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Taille maximale de batch pour les embeddings Ollama.
# Au-delà de 8 requêtes parallèles, la qualité cosine se dégrade.
EMBEDDING_BATCH_SIZE = 8


async def get_embedding(text: str, http_client: Optional[httpx.AsyncClient] = None) -> List[float]:
    embeddings = await get_embeddings([text], http_client)
    return embeddings[0]


async def get_embeddings(texts: List[str], http_client: Optional[httpx.AsyncClient] = None) -> List[List[float]]:
    """
    Obtient les embeddings pour une liste de textes via Ollama.
    Traitement par batchs de EMBEDDING_BATCH_SIZE (max 8) en parallèle
    pour préserver la qualité cosine tout en accélérant l'indexation.

    FIX : accepte un client HTTP partagé (app.state.http_client) pour éviter
    de créer un nouveau client à chaque appel.
    Si aucun client n'est fourni (ex: tests, scripts), un client local est créé.
    """
    if http_client is not None:
        return await _do_get_embeddings(texts, http_client)
    else:
        async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
            return await _do_get_embeddings(texts, client)


async def _do_get_embeddings(texts: List[str], client: httpx.AsyncClient) -> List[List[float]]:
    """
    Logique interne — requêtes Ollama par batchs de max EMBEDDING_BATCH_SIZE
    en parallèle avec asyncio.gather().
    L'ordre des embeddings est préservé.
    """
    results: List[List[float]] = []

    # Découper texts en batchs de EMBEDDING_BATCH_SIZE
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i:i + EMBEDDING_BATCH_SIZE]
        logger.debug(f"[Embedding] Batch {i // EMBEDDING_BATCH_SIZE + 1} : {len(batch)} chunks en parallèle")

        # Lancer tous les appels du batch en parallèle
        batch_embeddings = await asyncio.gather(*[
            _single_embedding(text, client) for text in batch
        ])

        results.extend(batch_embeddings)

    return results


async def _single_embedding(text: str, client: httpx.AsyncClient) -> List[float]:
    """Calcule l'embedding d'un seul texte."""
    response = await client.post(
        f"{settings.OLLAMA_BASE_URL}/api/embeddings",
        json={"model": settings.OLLAMA_EMBEDDING_MODEL, "prompt": text},
    )
    response.raise_for_status()
    embedding = response.json().get("embedding", [])
    if not embedding:
        raise ValueError(f"Embedding vide retourné pour : {text[:50]}")
    return embedding


async def verify_embedding_model(http_client: Optional[httpx.AsyncClient] = None) -> int:
    """Vérifie le modèle d'embedding et retourne sa dimension."""
    embedding = await get_embedding("test de dimension", http_client)
    dim = len(embedding)
    if dim == 0:
        raise ValueError("Le modèle d'embedding retourne des vecteurs vides")
    logger.info(f"Modèle d'embedding OK : {settings.OLLAMA_EMBEDDING_MODEL}, dim={dim}")
    return dim
