from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class KBCreate(BaseModel):
    name: str
    owner: str


class KBUpdate(BaseModel):
    name: Optional[str] = None


class KBOut(BaseModel):
    id: str
    name: str
    owner: str
    version: int
    content_hash: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KBDocumentOut(BaseModel):
    id: str
    kb_id: str
    filename: str
    content_type: str
    content_hash: str
    chunk_count: int
    tags: list[str] = []
    ingested_at: datetime

    model_config = {"from_attributes": True}


class KBFactCreate(BaseModel):
    key: str
    value: str
    source: Optional[str] = None


class KBFactOut(BaseModel):
    id: str
    kb_id: str
    key: str
    value: str
    source: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class KBLimitationCreate(BaseModel):
    description: str


class KBLimitationOut(BaseModel):
    id: str
    kb_id: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RetrieveRequest(BaseModel):
    text: str
    kb_ids: list[str]
    filters: Optional[dict] = None
    top_k: int = 5


class RetrievedChunk(BaseModel):
    chunk_text: str
    source: str
    score: float
    kb_id: str
    doc_id: str
    tags: list[str] = []


class RetrieveResponse(BaseModel):
    chunks: list[RetrievedChunk]
