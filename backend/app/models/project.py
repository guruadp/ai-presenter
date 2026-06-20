import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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
    deck_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
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
    show_files: Mapped[list["ShowFile"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ShowFile.version",
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
    content_hash: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped["Project"] = relationship(back_populates="slides")
    script: Mapped[Optional["ProjectSlideScript"]] = relationship(
        back_populates="slide",
        cascade="all, delete-orphan",
        uselist=False,
    )


class ProjectSlideScript(Base):
    __tablename__ = "project_slide_scripts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    slide_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("project_slides.id"),
        unique=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, default="draft", nullable=False)
    narration: Mapped[str] = mapped_column(Text, default="", nullable=False)
    segments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivery_style: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    running_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    revision_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tone_override: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    preview_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    stale_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    slide: Mapped["ProjectSlide"] = relationship(back_populates="script")


class ShowFile(Base):
    __tablename__ = "show_files"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_show_file_project_version"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, default="ready", nullable=False)
    manifest_path: Mapped[str] = mapped_column(String, nullable=False)
    bundle_path: Mapped[str] = mapped_column(String, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tts_provider: Mapped[str] = mapped_column(String, default="free-local", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped["Project"] = relationship(back_populates="show_files")


# ── EPIC 12 — Project Library & Reuse ─────────────────────────────────────────

class PresenterSession(Base):
    """One live presentation run — created when an orchestrator session starts."""
    __tablename__ = "presenter_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # = orchestrator session_id
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    show_file_id: Mapped[str] = mapped_column(String, ForeignKey("show_files.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    qa_entries: Mapped[list["QAEntry"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="QAEntry.created_at",
    )


class QAEntry(Base):
    """A single Q&A exchange that occurred during a presenter session."""
    __tablename__ = "qa_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("presenter_sessions.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String, default="general", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    deferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    slide_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    served_from_faq: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped["PresenterSession"] = relationship(back_populates="qa_entries")


class FAQ(Base):
    """Curated, pre-reviewed answers for frequent questions."""
    __tablename__ = "faqs"
    __table_args__ = (UniqueConstraint("project_id", "question", name="uq_faq_project_question"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_answer: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String, default="general", nullable=False)
    promoted_from_qa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pre_rendered_audio_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
