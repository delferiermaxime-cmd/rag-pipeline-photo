# -*- coding: utf-8 -*-
import logging
from typing import List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def get_embedding(text: str, http_client: Optional[httpx.AsyncClient] = None) -> List[float]:
    embeddings = await get_embeddings([text], http_client)
    return embeddings[0]


async def get_embeddings(texts: List[str], http_client: Optional[httpx.AsyncClient] = None) -> List[List[float]]:
    """
    Obtient les embeddings pour une liste de textes via Ollama.

    FIX : accepte un client HTTP partagé (app.state.http_client) pour éviter
    de créer un nouveau client à chaque appel.
    Si aucun client n'est fourni (ex: tests, scripts), un client local est créé.
    """
    if http_client is not None:
        # Cas normal en prod : on réutilise le client partagé
        return await _do_get_embeddings(texts, http_client)
    else:
        # Cas hors contexte FastAPI : on crée un client local temporaire
        async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
            return await _do_get_embeddings(texts, client)


async def _do_get_embeddings(texts: List[str], client: httpx.AsyncClient) -> List[List[float]]:
    """Logique interne — requêtes Ollama avec le client fourni."""
    results = []
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


async def verify_embedding_model(http_client: Optional[httpx.AsyncClient] = None) -> int:
    """Vérifie le modèle d'embedding et retourne sa dimension."""
    # FIX : passe le client partagé si disponible (appelé depuis main.py au démarrage)
    embedding = await get_embedding("test de dimension", http_client)
    dim = len(embedding)
    if dim == 0:
        raise ValueError("Le modèle d'embedding retourne des vecteurs vides")
    logger.info(f"Modèle d'embedding OK : {settings.OLLAMA_EMBEDDING_MODEL}, dim={dim}")
    return dim
