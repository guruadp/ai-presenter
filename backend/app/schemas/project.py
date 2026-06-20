from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
