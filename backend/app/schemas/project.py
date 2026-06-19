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
