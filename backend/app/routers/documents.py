# -*- coding: utf-8 -*-
import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.auth.dependencies import get_current_user
from app.models.database import AsyncSessionLocal, Document, DocumentImage, User, get_db
from app.models.schemas import DocumentOut
from app.services.docling_service import convert_document, IMAGES_DIR
from app.services.embedding_service import get_embeddings
from app.services.qdrant_service import delete_document_chunks, ensure_collection, upsert_chunks

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=DocumentOut, status_code=202)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    suffix = Path(file.filename).suffix.lower()
    suffix_clean = suffix.lstrip(".")
    if suffix_clean not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Format non supporté : '{suffix}'. Acceptés : {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}")

    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(413, f"Fichier trop volumineux ({len(content)//1024//1024} MB). Maximum : {settings.MAX_FILE_SIZE//1024//1024} MB")

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

    http_client = request.app.state.http_client
    background_tasks.add_task(
        _process_document,
        file_bytes=content,
        filename=file.filename,
        document_id=str(doc.id),
        user_id=str(current_user.id),
        http_client=http_client,
    )
    return doc


async def _process_document(
    file_bytes: bytes,
    filename: str,
    document_id: str,
    user_id: str,
    http_client=None,
) -> None:
    async with AsyncSessionLocal() as db:
        try:
            logger.info(f"[{document_id}] Début conversion Docling")
            chunks, images = await convert_document(file_bytes, filename, document_id)
            if not chunks:
                raise ValueError("Aucun chunk produit")

            # Sauvegarder les images en DB
            for img_data in images:
                db_image = DocumentImage(
                    document_id=UUID(document_id),
                    page=img_data["page"],
                    filename=img_data["filename"],
                    mime_type="image/png",
                )
                db.add(db_image)
            await db.flush()
            logger.info(f"[{document_id}] {len(images)} images sauvegardées en DB")

            # Enrichir les chunks avec les image_ids de leur page
            # Construire un index page → liste de filenames
            page_images: dict = {}
            for img_data in images:
                p = img_data["page"]
                page_images.setdefault(p, []).append(img_data["filename"])

            for chunk in chunks:
                chunk["image_filenames"] = page_images.get(chunk.get("page", 1), [])

            logger.info(f"[{document_id}] Embedding de {len(chunks)} chunks")
            texts = [c["content"] for c in chunks]
            embeddings = await get_embeddings(texts, http_client)

            await ensure_collection(len(embeddings[0]))
            count = await upsert_chunks(chunks, embeddings, user_id, document_id)

            doc = await db.get(Document, UUID(document_id))
            if doc:
                doc.status = "ready"
                doc.chunk_count = count
                await db.commit()
            logger.info(f"[{document_id}] Traité : {count} chunks, {len(images)} images")

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
    # Base partagée : tous les documents visibles par tous
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return result.scalars().all()


@router.get("/images/{filename}")
async def get_image(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """Sert une image extraite d'un document."""
    # Sécurité : empêcher path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Nom de fichier invalide")

    filepath = os.path.join(IMAGES_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "Image introuvable")

    return FileResponse(filepath, media_type="image/png")


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await db.get(Document, UUID(document_id))
    if not doc:
        raise HTTPException(404, "Document introuvable")

    # Supprimer les images sur disque
    result = await db.execute(
        select(DocumentImage).where(DocumentImage.document_id == UUID(document_id))
    )
    for img in result.scalars().all():
        try:
            filepath = os.path.join(IMAGES_DIR, img.filename)
            if os.path.exists(filepath):
                os.unlink(filepath)
        except OSError:
            pass

    await delete_document_chunks(document_id, str(current_user.id))
    await db.delete(doc)
