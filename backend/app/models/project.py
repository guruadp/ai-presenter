import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def default_tone_profile() -> dict:
    return {
        "formality": "balanced",
        "pace": "normal",
        "persona": "helpful presenter",
        "dos": [],
        "donts": [],
        "language": "en",
        "voice_id": None,
    }


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    tone_profile: Mapped[dict] = mapped_column(JSON, default=default_tone_profile, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    knowledge_bases: Mapped[list["ProjectKnowledgeBase"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    slides: Mapped[list["ProjectSlide"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectSlide.position",
    )


class ProjectKnowledgeBase(Base):
    __tablename__ = "project_knowledge_bases"
    __table_args__ = (UniqueConstraint("project_id", "kb_id", name="uq_project_kb"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    kb_id: Mapped[str] = mapped_column(String, ForeignKey("knowledge_bases.id"), nullable=False)
    pinned_version: Mapped[int] = mapped_column(Integer, nullable=False)
    pinned_content_hash: Mapped[str] = mapped_column(String, nullable=False)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped["Project"] = relationship(back_populates="knowledge_bases")


class ProjectSlide(Base):
    __tablename__ = "project_slides"
    __table_args__ = (UniqueConstraint("project_id", "position", name="uq_project_slide_position"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vision_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    generation_context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped["Project"] = relationship(back_populates="slides")
