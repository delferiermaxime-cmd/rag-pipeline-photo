# -*- coding: utf-8 -*-
import logging
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


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    return _client


async def ensure_collection(dim: int = None) -> None:
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


async def upsert_chunks(
    chunks: List[Dict[str, Any]],
    embeddings: List[List[float]],
    user_id: str,
    document_id: str,
) -> int:
    client = get_client()
    points = [
        PointStruct(
            id=str(uuid.uuid4()),  # FIX : uuid4 — pas hash() qui peut collisionner
            vector=embedding,
            payload={
                "user_id": user_id,
                "document_id": document_id,
                "title": chunk.get("title", ""),
                "page": chunk.get("page", 1),
                "content": chunk.get("content", ""),
                "chunk_index": chunk.get("chunk_index", i),
            },
        )
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    if points:
        await client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
    return len(points)


async def search_chunks(
    query_embedding: List[float],
    user_id: str,
    top_k: int = 5,
    document_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    client = get_client()
    must = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
    if document_ids:
        must.append(FieldCondition(key="document_id", match=MatchAny(any=document_ids)))

    results = await client.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=query_embedding,
        query_filter=Filter(must=must),
        limit=top_k,
        with_payload=True,
    )
    return [
        {
            "document_id": r.payload.get("document_id", ""),
            "title": r.payload.get("title", ""),
            "page": r.payload.get("page", 1),
            "content": r.payload.get("content", ""),
            "score": r.score,
        }
        for r in results
    ]


async def delete_document_chunks(document_id: str, user_id: str) -> None:
    client = get_client()
    await client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            ])
        ),
    )
    logger.info(f"Chunks supprimés pour document {document_id}")
