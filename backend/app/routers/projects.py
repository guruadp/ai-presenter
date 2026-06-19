import os
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.models.project import Project, ProjectKnowledgeBase, ProjectSlide
from app.schemas.project import ProjectCreate, ProjectOut, ProjectSlideOut, ProjectUpdate
from app.services import deck_ingestion, slide_vision

router = APIRouter(prefix="/projects", tags=["projects"])

DbDep = Annotated[Session, Depends(get_db)]


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _load_kbs_or_404(kb_ids: list[str], db: Session) -> list[KnowledgeBase]:
    kbs: list[KnowledgeBase] = []
    for kb_id in dict.fromkeys(kb_ids):
        kb = db.get(KnowledgeBase, kb_id)
        if not kb:
            raise HTTPException(404, f"Knowledge base not found: {kb_id}")
        kbs.append(kb)
    return kbs


def _set_project_kbs(project: Project, kb_ids: list[str], db: Session) -> None:
    kbs = _load_kbs_or_404(kb_ids, db)
    project.knowledge_bases = [
        ProjectKnowledgeBase(
            kb_id=kb.id,
            pinned_version=kb.version,
            pinned_content_hash=kb.content_hash,
        )
        for kb in kbs
    ]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: DbDep) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        name=body.name,
        owner=body.owner,
        tone_profile=body.tone_profile.model_dump(),
    )
    _set_project_kbs(project, body.kb_ids, db)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: DbDep) -> list[Project]:
    return db.query(Project).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: DbDep) -> Project:
    return _get_project_or_404(project_id, db)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate, db: DbDep) -> Project:
    project = _get_project_or_404(project_id, db)
    if body.name is not None:
        project.name = body.name
    if body.tone_profile is not None:
        project.tone_profile = body.tone_profile.model_dump()
    if body.kb_ids is not None:
        _set_project_kbs(project, body.kb_ids, db)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: DbDep) -> None:
    project = _get_project_or_404(project_id, db)
    db.delete(project)
    db.commit()


@router.get("/{project_id}/slides", response_model=list[ProjectSlideOut])
def list_slides(project_id: str, db: DbDep) -> list[ProjectSlide]:
    project = _get_project_or_404(project_id, db)
    return project.slides


@router.post("/{project_id}/deck", response_model=ProjectOut)
async def upload_deck(project_id: str, db: DbDep, file: UploadFile = File(...)) -> Project:
    project = _get_project_or_404(project_id, db)
    filename = file.filename or ""
    if not deck_ingestion.is_pptx(filename, file.content_type):
        raise HTTPException(400, "Only .pptx uploads are supported")

    content = await file.read()
    try:
        parsed_slides = deck_ingestion.parse_pptx(content)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    settings = get_settings()
    project_dir = os.path.join(settings.STORAGE_DIR, "projects", project.id)
    os.makedirs(project_dir, exist_ok=True)
    deck_path = os.path.join(project_dir, "source.pptx")
    with open(deck_path, "wb") as f:
        f.write(content)

    image_dir = os.path.join(project_dir, "slides")
    image_paths = deck_ingestion.render_slide_images(parsed_slides, image_dir)

    project.slides.clear()
    db.flush()
    for parsed_slide, image_path in zip(parsed_slides, image_paths):
        vision_summary = slide_vision.summarize_slide_image(image_path, parsed_slide)
        project.slides.append(
            ProjectSlide(
                position=parsed_slide.position,
                title=parsed_slide.title,
                body=parsed_slide.body,
                notes=parsed_slide.notes,
                image_path=image_path,
                vision_summary=vision_summary,
                generation_context=slide_vision.build_generation_context(
                    parsed_slide,
                    vision_summary,
                ),
            )
        )

    db.add(project)
    db.commit()
    db.refresh(project)
    return project
