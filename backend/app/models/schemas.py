# -*- coding: utf-8 -*-
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    id: UUID; email: str; username: str; role: str; is_active: bool; created_at: datetime
    model_config = {"from_attributes": True}

class DocumentOut(BaseModel):
    id: UUID; filename: str; original_name: str; file_type: str; status: str
    chunk_count: int; error_message: Optional[str]; created_at: datetime
    model_config = {"from_attributes": True}

class ChatMessageRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    model: str = Field(default="gemma3:4b")
    document_ids: Optional[List[str]] = None
    conversation_id: Optional[str] = None
    temperature: Optional[float] = 0.1
    top_k: Optional[int] = 5
    max_tokens: Optional[int] = 1024

ChatMessage = ChatMessageRequest

class MessageOut(BaseModel):
    id: UUID; role: str; content: str; created_at: datetime
    model_config = {"from_attributes": True}

class ConversationOut(BaseModel):
    id: UUID; title: str; created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}

class ConversationDetail(BaseModel):
    id: UUID; title: str; created_at: datetime; updated_at: datetime
    messages: List[MessageOut] = []
    model_config = {"from_attributes": True}

class ChatSource(BaseModel):
    document_id: str; title: str; page: Optional[int]; content: str; score: float
