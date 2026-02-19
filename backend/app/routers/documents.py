# -*- coding: utf-8 -*-
import asyncio
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

# FIX timeout : Docling peut bloquer sur un PDF complexe/corrompu
# On limite à 20 minutes maximum, après quoi le document passe en "error"
_DOCLING_TIMEOUT = 20 * 60  # 20 minutes en secondes


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
        raise HTTPException(
            400,
            f"Format non supporté : '{suffix}'. Acceptés : {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}"
        )

    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            413,
            f"Fichier trop volumineux ({len(content)//1024//1024} MB). "
            f"Maximum : {settings.MAX_FILE_SIZE//1024//1024} MB"
        )

    doc = Document(
        user_id=current_user.id,
        filename=f"{uuid4()}{suffix}",
        original_name=file.filename,
        file_type=suffix_clean,
        status="processing",
        progress=0,           # FIX progression : démarre à 0%
        status_detail="En attente de traitement",
    )
    db.add(doc)

    # FIX race condition : commit AVANT le background task
    await db.commit()
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


async def _update_progress(document_id: str, progress: int, detail: str) -> None:
    """Met à jour la progression du traitement en DB."""
    try:
        async with AsyncSessionLocal() as db:
            doc = await db.get(Document, UUID(document_id))
            if doc:
                doc.progress = progress
                doc.status_detail = detail
                await db.commit()
    except Exception as e:
        logger.warning(f"[{document_id}] Impossible de mettre à jour la progression : {e}")


async def _process_document(
    file_bytes: bytes,
    filename: str,
    document_id: str,
    user_id: str,
    http_client=None,
) -> None:
    """
    Pipeline complet : Docling → nettoyage → chunking → embedding → Qdrant.
    FIX timeout : enveloppé dans asyncio.wait_for avec _DOCLING_TIMEOUT secondes.
    FIX progression : mises à jour régulières visibles dans l'UI.
    """
    try:
        await asyncio.wait_for(
            _run_pipeline(file_bytes, filename, document_id, user_id, http_client),
            timeout=_DOCLING_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(f"[{document_id}] Timeout après {_DOCLING_TIMEOUT//60} minutes")
        await _set_error(document_id, f"Timeout : traitement trop long (>{_DOCLING_TIMEOUT//60} min). "
                                       "Le fichier est peut-être corrompu ou trop complexe.")


async def _run_pipeline(
    file_bytes: bytes,
    filename: str,
    document_id: str,
    user_id: str,
    http_client=None,
) -> None:
    """Pipeline effectif — séparé pour pouvoir appliquer le timeout dessus."""
    async with AsyncSessionLocal() as db:
        try:
            # Étape 1 : Conversion Docling
            await _update_progress(document_id, 10, "Conversion du document en cours…")
            logger.info(f"[{document_id}] Début conversion Docling")
            chunks, images = await convert_document(file_bytes, filename, document_id)
            if not chunks:
                raise ValueError("Aucun chunk produit après conversion")

            # Étape 2 : Sauvegarde des images
            await _update_progress(document_id, 40, f"Document converti : {len(chunks)} sections extraites. Sauvegarde des images…")
            for img_data in images:
                db_image = DocumentImage(
                    document_id=UUID(document_id),
                    page=img_data["page"],
                    filename=img_data["filename"],
                    mime_type="image/png",
                )
                db.add(db_image)
            await db.flush()
            logger.info(f"[{document_id}] {len(images)} images sauvegardées")

            # Enrichir les chunks avec les filenames d'images de leur page
            page_images: dict = {}
            for img_data in images:
                page_images.setdefault(img_data["page"], []).append(img_data["filename"])
            for chunk in chunks:
                chunk["image_filenames"] = page_images.get(chunk.get("page", 1), [])

            # Étape 3 : Embedding
            await _update_progress(document_id, 60, f"Calcul des embeddings ({len(chunks)} chunks)…")
            logger.info(f"[{document_id}] Embedding de {len(chunks)} chunks")
            texts = [c["content"] for c in chunks]
            embeddings = await get_embeddings(texts, http_client)

            # Étape 4 : Indexation Qdrant
            await _update_progress(document_id, 85, "Indexation dans la base vectorielle…")
            await ensure_collection(len(embeddings[0]))
            count = await upsert_chunks(chunks, embeddings, user_id, document_id)

            # Étape 5 : Finalisation
            doc = await db.get(Document, UUID(document_id))
            if doc:
                doc.status = "ready"
                doc.chunk_count = count
                doc.progress = 100
                doc.status_detail = f"Prêt — {count} chunks indexés, {len(images)} images"
                await db.commit()

            logger.info(f"[{document_id}] ✓ Traitement terminé : {count} chunks, {len(images)} images")

        except Exception as e:
            logger.error(f"[{document_id}] Erreur pipeline : {e}", exc_info=True)
            await _set_error(document_id, str(e)[:500])


async def _set_error(document_id: str, message: str) -> None:
    """Passe le document en statut error."""
    try:
        async with AsyncSessionLocal() as db:
            doc = await db.get(Document, UUID(document_id))
            if doc:
                doc.status = "error"
                doc.progress = 0
                doc.status_detail = message
                doc.error_message = message
                await db.commit()
    except Exception as e:
        logger.error(f"[{document_id}] Impossible de marquer l'erreur en DB : {e}")


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return result.scalars().all()


@router.get("/{document_id}/status", response_model=DocumentOut)
async def get_document_status(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    FIX progression : endpoint dédié pour poller le statut d'un document en cours
    de traitement. Le frontend peut appeler cet endpoint toutes les 2 secondes
    pour afficher une barre de progression.
    """
    doc = await db.get(Document, UUID(document_id))
    if not doc:
        raise HTTPException(404, "Document introuvable")
    return doc


@router.get("/images/{filename}")
async def get_image(
    filename: str,
    current_user: User = Depends(get_current_user),
):
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

    result = await db.execute(
        select(DocumentImage).where(DocumentImage.document_id == UUID(document_id))
    )
    images = result.scalars().all()

    await delete_document_chunks(document_id, str(current_user.id))
    await db.delete(doc)

    # FIX : commit DB avant suppression fichiers disque
    await db.commit()

    for img in images:
        try:
            filepath = os.path.join(IMAGES_DIR, img.filename)
            if os.path.exists(filepath):
                os.unlink(filepath)
        except OSError as e:
            logger.warning(f"Impossible de supprimer l'image {img.filename}: {e}")
