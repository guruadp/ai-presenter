import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    documents: Mapped[list["KBDocument"]] = relationship(back_populates="kb", cascade="all, delete-orphan")
    facts: Mapped[list["KBFact"]] = relationship(back_populates="kb", cascade="all, delete-orphan")
    limitations: Mapped[list["KBLimitation"]] = relationship(back_populates="kb", cascade="all, delete-orphan")


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    kb_id: Mapped[str] = mapped_column(String, ForeignKey("knowledge_bases.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    kb: Mapped["KnowledgeBase"] = relationship(back_populates="documents")


class KBFact(Base):
    __tablename__ = "kb_facts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    kb_id: Mapped[str] = mapped_column(String, ForeignKey("knowledge_bases.id"), nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    kb: Mapped["KnowledgeBase"] = relationship(back_populates="facts")


class KBLimitation(Base):
    __tablename__ = "kb_limitations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    kb_id: Mapped[str] = mapped_column(String, ForeignKey("knowledge_bases.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    kb: Mapped["KnowledgeBase"] = relationship(back_populates="limitations")
