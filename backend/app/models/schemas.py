# -*- coding: utf-8 -*-
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)

    @field_validator('username')
    @classmethod
    def username_valid(cls, v):
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError("Le nom d'utilisateur ne peut contenir que des lettres, chiffres, _ et -")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    email: str
    username: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Documents ─────────────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    id: UUID
    filename: str
    original_name: str
    file_type: str
    status: str
    chunk_count: int
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Chat ──────────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    model: str = Field(default="gemma3:4b")
    document_ids: Optional[List[str]] = None


class ChatSource(BaseModel):
    document_id: str
    title: str
    page: Optional[int]
    content: str
    score: float
