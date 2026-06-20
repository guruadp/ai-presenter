from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class ToneProfile(BaseModel):
    formality: str = "balanced"
    pace: str = "normal"
    persona: str = "helpful presenter"
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    language: str = "en"
    voice_id: Optional[str] = None


class ProjectCreate(BaseModel):
    name: str
    owner: str
    kb_ids: list[str] = Field(default_factory=list)
    tone_profile: ToneProfile = Field(default_factory=ToneProfile)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    kb_ids: Optional[list[str]] = None
    tone_profile: Optional[ToneProfile] = None


class ProjectKnowledgeBaseOut(BaseModel):
    kb_id: str
    pinned_version: int
    pinned_content_hash: str
    attached_at: datetime

    model_config = {"from_attributes": True}


class ProjectSlideScriptOut(BaseModel):
    id: str
    slide_id: str
    status: str
    narration: str
    segments: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    duration_seconds: int
    delivery_style: dict = Field(default_factory=dict)
    running_summary: str
    feedback: Optional[str] = None
    revision_history: list[dict] = Field(default_factory=list)
    tone_override: dict = Field(default_factory=dict)
    preview_config: dict = Field(default_factory=dict)
    stale_reasons: list[str] = Field(default_factory=list)
    version: int
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RegenerateScriptRequest(BaseModel):
    feedback: Optional[str] = None
    make_shorter: bool = False
    more_energy: bool = False
    more_citations: bool = False
    tone_override: dict = Field(default_factory=dict)


class ScriptEditRequest(BaseModel):
    narration: str


class ScriptReviewSettingsRequest(BaseModel):
    tone_override: dict = Field(default_factory=dict)
    preview_config: dict = Field(default_factory=dict)


class ScriptAudioPreviewRequest(BaseModel):
    preview_config: dict = Field(default_factory=dict)


class ProjectSlideOut(BaseModel):
    id: str
    project_id: str
    position: int
    title: Optional[str] = None
    body: str
    notes: str
    image_path: Optional[str] = None
    vision_summary: str = ""
    generation_context: dict = Field(default_factory=dict)
    content_hash: str = ""
    script: Optional[ProjectSlideScriptOut] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ShowFileOut(BaseModel):
    id: str
    project_id: str
    version: int
    status: str
    manifest_path: str
    bundle_path: str
    manifest: dict = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)
    tts_provider: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PackageGateOut(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)


class LiveTTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    name: str
    owner: str
    tone_profile: ToneProfile
    knowledge_bases: list[ProjectKnowledgeBaseOut]
    slides: list[ProjectSlideOut] = []
    show_files: list[ShowFileOut] = []
    deck_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── EPIC 12 schemas ───────────────────────────────────────────────────────────

class PresenterSessionOut(BaseModel):
    id: str
    project_id: str
    show_file_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class QAEntryOut(BaseModel):
    id: str
    session_id: str
    project_id: str
    question: str
    answer_text: str
    question_type: str
    confidence: float
    deferred: bool
    slide_index: int
    served_from_faq: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LogQARequest(BaseModel):
    question: str
    answer: str
    question_type: str = "general"
    confidence: float = 0.0
    deferred: bool = False
    slide_index: int = 0
    served_from_faq: bool = False


class QAAnalyticsOut(BaseModel):
    total_questions: int
    deferred_count: int
    deferral_rate: float
    faq_hit_count: int
    type_distribution: dict[str, int]
    top_questions: list[dict]
    per_slide_counts: dict[str, int]


class FAQOut(BaseModel):
    id: str
    project_id: str
    question: str
    canonical_answer: str
    question_type: str
    promoted_from_qa: bool
    approved: bool
    pre_rendered_audio_path: Optional[str] = None
    hit_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FAQCandidateOut(BaseModel):
    question: str
    question_type: str
    answer_text: str
    confidence: float
    occurrence_count: int


class CreateFAQRequest(BaseModel):
    question: str
    canonical_answer: str
    question_type: str = "general"
    promoted_from_qa: bool = False


class UpdateFAQRequest(BaseModel):
    canonical_answer: Optional[str] = None
    question_type: Optional[str] = None
    approved: Optional[bool] = None
