import os
import uuid
from datetime import datetime, timezone
from typing import Annotated

import tempfile

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.models.project import Project, ProjectKnowledgeBase, ProjectSlide
from app.schemas.project import (
    LiveTTSRequest,
    PackageGateOut,
    ProjectCreate,
    ProjectOut,
    ProjectSlideOut,
    ProjectSlideScriptOut,
    ProjectUpdate,
    RegenerateScriptRequest,
    ScriptAudioPreviewRequest,
    ScriptEditRequest,
    ScriptReviewSettingsRequest,
    ShowFileOut,
)
from app.services import deck_ingestion, script_generation, show_file, slide_vision
from app.services.tts import get_tts_provider

router = APIRouter(prefix="/projects", tags=["projects"])

DbDep = Annotated[Session, Depends(get_db)]


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _get_project_slide_or_404(project: Project, slide_id: str) -> ProjectSlide:
    for slide in project.slides:
        if slide.id == slide_id:
            return slide
    raise HTTPException(404, "Slide not found")


def _get_slide_script_or_404(project: Project, slide_id: str):
    slide = _get_project_slide_or_404(project, slide_id)
    if not slide.script:
        raise HTTPException(404, "Script not found")
    return slide.script


def _mark_stale_scripts_for_kb_changes(project: Project, db: Session) -> None:
    for link in project.knowledge_bases:
        kb = db.get(KnowledgeBase, link.kb_id)
        if not kb:
            continue
        if kb.version != link.pinned_version or kb.content_hash != link.pinned_content_hash:
            reason = f"KB version changed: {kb.name} v{link.pinned_version} -> v{kb.version}"
            for slide in project.slides:
                if slide.script and slide.script.status == "approved":
                    reasons = list(slide.script.stale_reasons or [])
                    if reason not in reasons:
                        slide.script.stale_reasons = [*reasons, reason]
                    slide.script.status = "stale"


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
    projects = db.query(Project).all()
    for project in projects:
        _mark_stale_scripts_for_kb_changes(project, db)
    db.commit()
    return projects


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: DbDep) -> Project:
    project = _get_project_or_404(project_id, db)
    _mark_stale_scripts_for_kb_changes(project, db)
    db.commit()
    db.refresh(project)
    return project


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


@router.get("/{project_id}/package-gate", response_model=PackageGateOut)
def get_package_gate(project_id: str, db: DbDep) -> dict:
    project = _get_project_or_404(project_id, db)
    _mark_stale_scripts_for_kb_changes(project, db)
    db.commit()
    errors = show_file.validate_packaging_gate(project)
    return {"ok": not errors, "errors": errors}


@router.get("/{project_id}/show-files", response_model=list[ShowFileOut])
def list_show_files(project_id: str, db: DbDep):
    project = _get_project_or_404(project_id, db)
    return project.show_files


@router.post("/{project_id}/show-files", response_model=ShowFileOut, status_code=201)
def package_project_show_file(project_id: str, db: DbDep):
    project = _get_project_or_404(project_id, db)
    _mark_stale_scripts_for_kb_changes(project, db)
    errors = show_file.validate_packaging_gate(project)
    if errors:
        raise HTTPException(400, {"message": "Show File packaging gate failed", "errors": errors})
    packaged = show_file.package_show_file(project)
    db.add(packaged)
    db.commit()
    db.refresh(packaged)
    return packaged


@router.get("/{project_id}/show-files/{show_file_id}", response_model=ShowFileOut)
def get_show_file(project_id: str, show_file_id: str, db: DbDep):
    project = _get_project_or_404(project_id, db)
    for item in project.show_files:
        if item.id == show_file_id:
            return item
    raise HTTPException(404, "Show File not found")


@router.post("/{project_id}/show-files/{show_file_id}/validate", response_model=ShowFileOut)
def validate_show_file(project_id: str, show_file_id: str, db: DbDep):
    project = _get_project_or_404(project_id, db)
    for item in project.show_files:
        if item.id == show_file_id:
            show_dir = os.path.dirname(item.manifest_path)
            item.validation_errors = show_file.validate_show_bundle(show_dir, item.manifest)
            item.status = "ready" if not item.validation_errors else "invalid"
            db.add(item)
            db.commit()
            db.refresh(item)
            return item
    raise HTTPException(404, "Show File not found")


@router.get("/{project_id}/show-files/{show_file_id}/download")
def download_show_file(project_id: str, show_file_id: str, db: DbDep) -> FileResponse:
    project = _get_project_or_404(project_id, db)
    for item in project.show_files:
        if item.id == show_file_id:
            if not os.path.exists(item.bundle_path):
                raise HTTPException(404, "Show File bundle not found")
            return FileResponse(
                item.bundle_path,
                media_type="application/zip",
                filename=f"{project.name.replace(' ', '_')}_show_v{item.version}.zip",
            )
    raise HTTPException(404, "Show File not found")


@router.get("/{project_id}/show-files/{show_file_id}/assets/{asset_path:path}")
def get_show_file_asset(
    project_id: str,
    show_file_id: str,
    asset_path: str,
    db: DbDep,
) -> FileResponse:
    project = _get_project_or_404(project_id, db)
    for item in project.show_files:
        if item.id != show_file_id:
            continue
        show_dir = os.path.abspath(os.path.dirname(item.manifest_path))
        requested = os.path.abspath(os.path.join(show_dir, asset_path))
        if not requested.startswith(show_dir + os.sep):
            raise HTTPException(400, "Invalid Show File asset path")
        if not os.path.exists(requested):
            raise HTTPException(404, "Show File asset not found")
        media_type = "image/png" if requested.lower().endswith(".png") else "application/octet-stream"
        if requested.lower().endswith(".wav"):
            media_type = "audio/wav"
        return FileResponse(requested, media_type=media_type)
    raise HTTPException(404, "Show File not found")


@router.get("/{project_id}/slides/{slide_id}/image")
def get_slide_image(project_id: str, slide_id: str, db: DbDep) -> FileResponse:
    project = _get_project_or_404(project_id, db)
    slide = _get_project_slide_or_404(project, slide_id)
    if not slide.image_path or not os.path.exists(slide.image_path):
        raise HTTPException(404, "Slide image not found")
    return FileResponse(slide.image_path, media_type="image/png")


@router.post("/{project_id}/scripts", response_model=ProjectOut)
def generate_scripts(project_id: str, db: DbDep) -> Project:
    project = _get_project_or_404(project_id, db)
    if not project.slides:
        raise HTTPException(400, "Upload a deck before generating scripts")

    script_generation.generate_project_scripts(project, db)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.post(
    "/{project_id}/slides/{slide_id}/script/regenerate",
    response_model=ProjectSlideScriptOut,
)
def regenerate_slide_script(
    project_id: str,
    slide_id: str,
    body: RegenerateScriptRequest,
    db: DbDep,
):
    project = _get_project_or_404(project_id, db)
    slide = _get_project_slide_or_404(project, slide_id)
    options = script_generation.GenerationOptions(
        feedback=body.feedback,
        make_shorter=body.make_shorter,
        more_energy=body.more_energy,
        more_citations=body.more_citations,
        tone_override=body.tone_override,
    )
    script = script_generation.regenerate_slide_script(project, slide, db, options)
    db.commit()
    db.refresh(script)
    return script


@router.patch(
    "/{project_id}/slides/{slide_id}/script",
    response_model=ProjectSlideScriptOut,
)
def edit_slide_script(
    project_id: str,
    slide_id: str,
    body: ScriptEditRequest,
    db: DbDep,
):
    project = _get_project_or_404(project_id, db)
    script = _get_slide_script_or_404(project, slide_id)
    if not body.narration.strip():
        raise HTTPException(400, "Narration cannot be empty")
    script_generation.edit_script(script, body.narration)
    db.add(script)
    db.commit()
    db.refresh(script)
    return script


@router.post(
    "/{project_id}/slides/{slide_id}/script/revert",
    response_model=ProjectSlideScriptOut,
)
def revert_slide_script(project_id: str, slide_id: str, db: DbDep):
    project = _get_project_or_404(project_id, db)
    script = _get_slide_script_or_404(project, slide_id)
    if not script.revision_history:
        raise HTTPException(400, "No previous script version to revert to")
    script_generation.revert_script(script)
    db.add(script)
    db.commit()
    db.refresh(script)
    return script


@router.post(
    "/{project_id}/slides/{slide_id}/script/approve",
    response_model=ProjectSlideScriptOut,
)
def approve_slide_script(project_id: str, slide_id: str, db: DbDep):
    project = _get_project_or_404(project_id, db)
    script = _get_slide_script_or_404(project, slide_id)
    if not script.narration.strip():
        raise HTTPException(400, "Cannot approve an empty script")
    if not script.duration_seconds:
        raise HTTPException(400, "Cannot approve a script without duration")
    script.status = "approved"
    script.stale_reasons = []
    script.approved_at = datetime.now(timezone.utc)
    db.add(script)
    db.commit()
    db.refresh(script)
    return script


@router.patch(
    "/{project_id}/slides/{slide_id}/script/review-settings",
    response_model=ProjectSlideScriptOut,
)
def update_script_review_settings(
    project_id: str,
    slide_id: str,
    body: ScriptReviewSettingsRequest,
    db: DbDep,
):
    project = _get_project_or_404(project_id, db)
    script = _get_slide_script_or_404(project, slide_id)
    script.tone_override = body.tone_override
    script.preview_config = body.preview_config
    db.add(script)
    db.commit()
    db.refresh(script)
    return script


@router.post("/{project_id}/slides/{slide_id}/script/segments/{segment_index}/preview-audio")
def preview_segment_audio(
    project_id: str,
    slide_id: str,
    segment_index: int,
    body: ScriptAudioPreviewRequest,
    db: DbDep,
) -> FileResponse:
    project = _get_project_or_404(project_id, db)
    script = _get_slide_script_or_404(project, slide_id)
    segment = next(
        (item for item in script.segments if int(item.get("index", 0)) == segment_index),
        None,
    )
    if not segment:
        raise HTTPException(404, "Segment not found")

    settings = get_settings()
    preview_dir = os.path.join(settings.STORAGE_DIR, "projects", project.id, "audio_previews")
    os.makedirs(preview_dir, exist_ok=True)
    output_path = os.path.join(
        preview_dir,
        f"slide_{slide_id}_script_v{script.version}_segment_{segment_index}.wav",
    )
    preview_config = {**(script.preview_config or {}), **(body.preview_config or {})}
    voice_id = (
        preview_config.get("voice_id")
        or script.tone_override.get("voice_id")
        or (project.tone_profile or {}).get("voice_id")
    )
    get_tts_provider().synthesize(
        text=segment.get("text", ""),
        output_path=output_path,
        voice_id=voice_id,
        preview_config=preview_config,
    )
    return FileResponse(output_path, media_type="audio/wav", filename=f"slide_{slide_id}_segment_{segment_index}.wav")


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
    image_paths = deck_ingestion.render_slide_images(parsed_slides, image_dir, pptx_path=deck_path)

    existing_by_position = {slide.position: slide for slide in project.slides}
    seen_positions = set()
    for parsed_slide, image_path in zip(parsed_slides, image_paths):
        seen_positions.add(parsed_slide.position)
        vision_summary = slide_vision.summarize_slide_image(image_path, parsed_slide)
        existing_slide = existing_by_position.get(parsed_slide.position)
        if existing_slide:
            changed = (
                existing_slide.title != parsed_slide.title
                or existing_slide.body != parsed_slide.body
                or existing_slide.notes != parsed_slide.notes
            )
            existing_slide.title = parsed_slide.title
            existing_slide.body = parsed_slide.body
            existing_slide.notes = parsed_slide.notes
            existing_slide.image_path = image_path
            existing_slide.vision_summary = vision_summary
            existing_slide.generation_context = slide_vision.build_generation_context(
                parsed_slide,
                vision_summary,
            )
            if changed and existing_slide.script:
                existing_slide.script.status = "stale"
                reasons = list(existing_slide.script.stale_reasons or [])
                reason = "Slide content changed after deck upload"
                if reason not in reasons:
                    existing_slide.script.stale_reasons = [*reasons, reason]
        else:
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
                ),
            )

    for position, slide in existing_by_position.items():
        if position not in seen_positions:
            db.delete(slide)

    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/show-files/{show_file_id}/tts/speak")
def speak_live_tts(
    project_id: str,
    show_file_id: str,
    body: LiveTTSRequest,
    background_tasks: BackgroundTasks,
    db: DbDep,
) -> FileResponse:
    project = _get_project_or_404(project_id, db)
    sf = next((sf for sf in project.show_files if sf.id == show_file_id), None)
    if not sf:
        raise HTTPException(404, "Show File not found")

    voice_id = body.voice_id or (sf.manifest or {}).get("voice_config", {}).get("voice_id")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    get_tts_provider().synthesize(body.text, tmp_path, voice_id=voice_id)
    background_tasks.add_task(os.unlink, tmp_path)
    return FileResponse(tmp_path, media_type="audio/wav")
