# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user
from app.models.database import Document, User, get_db
from app.models.schemas import UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
    # FIX : pagination pour éviter de charger toute la table d'un coup
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    # FIX : or 0 sur tous les scalaires — func.count/sum peut retourner None
    user_count  = await db.scalar(select(func.count(User.id))) or 0
    doc_count   = await db.scalar(select(func.count(Document.id))) or 0
    ready_docs  = await db.scalar(
        select(func.count(Document.id)).where(Document.status == "ready")
    ) or 0
    total_chunks = await db.scalar(select(func.sum(Document.chunk_count))) or 0

    return {
        "total_users":      user_count,
        "total_documents":  doc_count,
        "ready_documents":  ready_docs,
        "total_chunks":     total_chunks,
    }
