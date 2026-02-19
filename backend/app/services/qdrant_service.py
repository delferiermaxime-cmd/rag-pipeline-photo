# -*- coding: utf-8 -*-
import logging
import math
import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, FilterSelector,
    MatchAny, MatchValue, PointStruct, VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncQdrantClient] = None
_collection_ready: bool = False


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    return _client


async def ensure_collection(dim: int = None) -> None:
    global _collection_ready
    if _collection_ready:
        return
    client = get_client()
    dim = dim or settings.EMBEDDING_DIM
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if settings.QDRANT_COLLECTION not in names:
        await client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        logger.info(f"Collection '{settings.QDRANT_COLLECTION}' créée (dim={dim})")
    else:
        logger.info(f"Collection '{settings.QDRANT_COLLECTION}' déjà existante (dim={dim})")
    _collection_ready = True


async def upsert_chunks(
    chunks: List[Dict[str, Any]],
    embeddings: List[List[float]],
    user_id: str,
    document_id: str,
) -> int:
    client = get_client()
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "document_id": document_id,
                "title": chunk.get("title", ""),
                "page": chunk.get("page", 1),
                "content": chunk.get("content", ""),
                "chunk_index": chunk.get("chunk_index", i),
                "image_filenames": chunk.get("image_filenames", []),
            },
        )
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    if points:
        await client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
    return len(points)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calcule la similarité cosinus entre deux vecteurs."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _mmr_rerank(
    candidates: List[Dict[str, Any]],
    query_embedding: List[float],
    top_k: int,
    lambda_mmr: float = 0.6,
) -> List[Dict[str, Any]]:
    """
    Maximum Marginal Relevance : sélectionne top_k chunks en maximisant
    à la fois la pertinence (similarité avec la requête) et la diversité
    (dissimilarité avec les chunks déjà sélectionnés).

    lambda_mmr : 1.0 = tri par pertinence pure, 0.0 = diversité pure.
    0.6 = bon équilibre pertinence/diversité.
    """
    if not candidates:
        return []

    # On a déjà les scores de pertinence depuis Qdrant
    selected = []
    remaining = list(candidates)

    while len(selected) < top_k and remaining:
        if not selected:
            # Premier chunk : prendre le plus pertinent
            best = max(remaining, key=lambda c: c["score"])
        else:
            # Suivants : maximiser score MMR
            def mmr_score(c):
                relevance = c["score"]
                # Similarité max avec les chunks déjà sélectionnés
                max_sim = max(
                    _cosine_similarity(c["vector"], s["vector"])
                    for s in selected
                )
                return lambda_mmr * relevance - (1 - lambda_mmr) * max_sim

            best = max(remaining, key=mmr_score)

        selected.append(best)
        remaining.remove(best)

    # Retrier les sélectionnés par score de pertinence pour l'affichage
    selected.sort(key=lambda c: c["score"], reverse=True)
    return selected


async def search_chunks(
    query_embedding: List[float],
    user_id: str = None,
    top_k: int = 8,
    document_ids: Optional[List[str]] = None,
    min_score: float = 0.0,
    use_mmr: bool = True,
    mmr_lambda: float = 0.6,
) -> List[Dict[str, Any]]:
    """
    Recherche les chunks les plus pertinents.
    Si use_mmr=True, applique MMR pour diversifier les résultats
    (évite de retourner plusieurs chunks très similaires du même document).
    """
    client = get_client()
    query_filter = None
    if document_ids:
        query_filter = Filter(must=[
            FieldCondition(key="document_id", match=MatchAny(any=document_ids))
        ])

    # Récupérer plus de candidats pour MMR (3x top_k, min 20)
    fetch_k = max(top_k * 3, 20) if use_mmr else top_k

    results = await client.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=query_embedding,
        query_filter=query_filter,
        limit=fetch_k,
        score_threshold=min_score if min_score > 0 else None,
        with_payload=True,
        with_vectors=use_mmr,  # nécessaire pour MMR
    )

    candidates = [
        {
            "document_id": r.payload.get("document_id", ""),
            "title": r.payload.get("title", ""),
            "page": r.payload.get("page", 1),
            "content": r.payload.get("content", ""),
            "score": r.score,
            "image_filenames": r.payload.get("image_filenames", []),
            "vector": list(r.vector) if use_mmr and r.vector else [],
        }
        for r in results
    ]

    if use_mmr and len(candidates) > top_k:
        logger.info(f"MMR : {len(candidates)} candidats → {top_k} chunks diversifiés")
        candidates = _mmr_rerank(candidates, query_embedding, top_k, mmr_lambda)

    # Supprimer le vecteur de la réponse finale (inutile pour le frontend)
    for c in candidates:
        c.pop("vector", None)

    return candidates[:top_k]


async def delete_document_chunks(document_id: str, user_id: str = None) -> None:
    client = get_client()
    await client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
            ])
        ),
    )
    logger.info(f"Chunks supprimés pour document {document_id}")
