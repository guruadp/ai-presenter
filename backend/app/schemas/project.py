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
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RegenerateScriptRequest(BaseModel):
    feedback: Optional[str] = None
    make_shorter: bool = False
    more_energy: bool = False
    more_citations: bool = False


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


class ProjectOut(BaseModel):
    id: str
    name: str
    owner: str
    tone_profile: ToneProfile
    knowledge_bases: list[ProjectKnowledgeBaseOut]
    slides: list[ProjectSlideOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
