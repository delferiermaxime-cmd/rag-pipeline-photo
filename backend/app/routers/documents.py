# -*- coding: utf-8 -*-
import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.auth.dependencies import get_current_user
from app.models.database import AsyncSessionLocal, Document, User, get_db
from app.models.schemas import DocumentOut
from app.services.docling_service import convert_document
from app.services.embedding_service import get_embeddings
from app.services.qdrant_service import delete_document_chunks, ensure_collection, upsert_chunks

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=DocumentOut, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validation extension (sans point, comme dans ALLOWED_EXTENSIONS)
    suffix = Path(file.filename).suffix.lower()
    suffix_clean = suffix.lstrip(".")
    if suffix_clean not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Format non supporté : '{suffix}'. "
            f"Acceptés : {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            413,
            f"Fichier trop volumineux ({len(content)//1024//1024} MB). "
            f"Maximum : {settings.MAX_FILE_SIZE//1024//1024} MB",
        )

    doc = Document(
        user_id=current_user.id,
        filename=f"{uuid4()}{suffix}",
        original_name=file.filename,
        file_type=suffix_clean,
        status="processing",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    # commit géré par get_db

    background_tasks.add_task(
        _process_document,
        file_bytes=content,
        filename=file.filename,
        document_id=str(doc.id),
        user_id=str(current_user.id),
    )
    return doc


async def _process_document(file_bytes: bytes, filename: str, document_id: str, user_id: str) -> None:
    """
    Tâche de fond : Docling → chunks → embeddings → Qdrant → mise à jour DB.
    FIX : docling_service.convert_document retourne déjà les chunks, pas un str brut.
    FIX : db.get(Document, UUID(document_id)) — UUID requis, pas str.
    """
    async with AsyncSessionLocal() as db:
        try:
            logger.info(f"[{document_id}] Début conversion Docling")
            chunks = await convert_document(file_bytes, filename)
            if not chunks:
                raise ValueError("Docling n'a produit aucun chunk")

            logger.info(f"[{document_id}] Embedding de {len(chunks)} chunks")
            texts = [c["content"] for c in chunks]
            embeddings = await get_embeddings(texts)

            await ensure_collection(len(embeddings[0]))
            count = await upsert_chunks(chunks, embeddings, user_id, document_id)

            doc = await db.get(Document, UUID(document_id))
            if doc:
                doc.status = "ready"
                doc.chunk_count = count
                await db.commit()
            logger.info(f"[{document_id}] Traité : {count} chunks")

        except Exception as e:
            logger.error(f"[{document_id}] Erreur : {e}", exc_info=True)
            try:
                doc = await db.get(Document, UUID(document_id))
                if doc:
                    doc.status = "error"
                    doc.error_message = str(e)[:500]
                    await db.commit()
            except Exception:
                pass


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await db.get(Document, UUID(document_id))
    if not doc:
        raise HTTPException(404, "Document introuvable")
    if str(doc.user_id) != str(current_user.id):
        raise HTTPException(403, "Accès refusé")

    await delete_document_chunks(document_id, str(current_user.id))
    await db.delete(doc)
    # commit géré par get_db
