# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends
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
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    user_count = await db.scalar(select(func.count(User.id)))
    doc_count = await db.scalar(select(func.count(Document.id)))
    ready_docs = await db.scalar(
        select(func.count(Document.id)).where(Document.status == "ready")
    )
    total_chunks = await db.scalar(select(func.sum(Document.chunk_count))) or 0
    return {
        "total_users": user_count,
        "total_documents": doc_count,
        "ready_documents": ready_docs,
        "total_chunks": total_chunks,
    }
