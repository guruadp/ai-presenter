import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated

import tempfile

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.models.project import FAQ, Project, ProjectKnowledgeBase, ProjectSlide, PresenterSession, QAEntry
from app.schemas.project import (
    CreateFAQRequest,
    FAQCandidateOut,
    FAQOut,
    LiveTTSRequest,
    PackageGateOut,
    ProjectCreate,
    ProjectOut,
    ProjectSlideOut,
    ProjectSlideScriptOut,
    ProjectUpdate,
    QAAnalyticsOut,
    QAEntryOut,
    RegenerateScriptRequest,
    ScriptAudioPreviewRequest,
    ScriptEditRequest,
    ScriptReviewSettingsRequest,
    ShowFileOut,
    UpdateFAQRequest,
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
    return (
        db.query(Project)
        .options(
            selectinload(Project.knowledge_bases),
            selectinload(Project.show_files),
            selectinload(Project.slides).selectinload(ProjectSlide.script),
        )
        .all()
    )


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


def _slide_content_hash(title: str | None, body: str, notes: str) -> str:
    raw = f"{title or ''}\n{body}\n{notes}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


@router.post("/{project_id}/deck", response_model=ProjectOut)
async def upload_deck(project_id: str, db: DbDep, file: UploadFile = File(...)) -> Project:
    project = _get_project_or_404(project_id, db)
    filename = file.filename or ""
    if not deck_ingestion.is_pptx(filename, file.content_type):
        raise HTTPException(400, "Only .pptx uploads are supported")

    content = await file.read()
    new_deck_hash = hashlib.sha256(content).hexdigest()

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
        new_hash = _slide_content_hash(parsed_slide.title, parsed_slide.body, parsed_slide.notes)
        existing_slide = existing_by_position.get(parsed_slide.position)
        if existing_slide:
            # S12.2: skip expensive Vision API call when content is unchanged
            content_changed = existing_slide.content_hash != new_hash
            if content_changed:
                vision_summary = slide_vision.summarize_slide_image(image_path, parsed_slide)
                existing_slide.title = parsed_slide.title
                existing_slide.body = parsed_slide.body
                existing_slide.notes = parsed_slide.notes
                existing_slide.vision_summary = vision_summary
                existing_slide.generation_context = slide_vision.build_generation_context(
                    parsed_slide, vision_summary,
                )
                existing_slide.content_hash = new_hash
                if existing_slide.script:
                    existing_slide.script.status = "stale"
                    reasons = list(existing_slide.script.stale_reasons or [])
                    reason = "Slide content changed after deck upload"
                    if reason not in reasons:
                        existing_slide.script.stale_reasons = [*reasons, reason]
            existing_slide.image_path = image_path
        else:
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
                        parsed_slide, vision_summary,
                    ),
                    content_hash=new_hash,
                ),
            )

    for position, slide in existing_by_position.items():
        if position not in seen_positions:
            db.delete(slide)

    project.deck_hash = new_deck_hash
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/show-files/{show_file_id}/export/video")
def export_video(
    project_id: str,
    show_file_id: str,
    background_tasks: BackgroundTasks,
    db: DbDep,
) -> FileResponse:
    project = _get_project_or_404(project_id, db)
    sf = next((sf for sf in project.show_files if sf.id == show_file_id), None)
    if not sf:
        raise HTTPException(404, "Show File not found")
    if sf.status != "ready":
        raise HTTPException(422, "Show File is not in ready state")

    # Write to a temp file; background task deletes it after the response is sent
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    video_path = tmp.name

    from app.services.video_export import export_show_video
    try:
        export_show_video(project, show_file_id, video_path)
    except ValueError as exc:
        os.unlink(video_path)
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        os.unlink(video_path)
        raise HTTPException(500, str(exc)) from exc

    background_tasks.add_task(os.unlink, video_path)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in project.name)
    filename = f"{safe_name}_presentation.mp4"
    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


# ── EPIC 12 — S12.3 Q&A history + analytics ──────────────────────────────────

@router.get("/{project_id}/qa-history", response_model=list[QAEntryOut])
def get_qa_history(project_id: str, db: DbDep, limit: int = 200) -> list[QAEntry]:
    _get_project_or_404(project_id, db)
    return (
        db.query(QAEntry)
        .filter(QAEntry.project_id == project_id)
        .order_by(QAEntry.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/{project_id}/qa-analytics", response_model=QAAnalyticsOut)
def get_qa_analytics(project_id: str, db: DbDep) -> dict:
    _get_project_or_404(project_id, db)
    entries: list[QAEntry] = (
        db.query(QAEntry).filter(QAEntry.project_id == project_id).all()
    )
    total = len(entries)
    if total == 0:
        return {
            "total_questions": 0,
            "deferred_count": 0,
            "deferral_rate": 0.0,
            "faq_hit_count": 0,
            "type_distribution": {},
            "top_questions": [],
            "per_slide_counts": {},
        }

    deferred = sum(1 for e in entries if e.deferred)
    faq_hits = sum(1 for e in entries if e.served_from_faq)

    type_dist: dict[str, int] = {}
    for e in entries:
        type_dist[e.question_type] = type_dist.get(e.question_type, 0) + 1

    # top questions by frequency
    q_count: dict[str, dict] = {}
    for e in entries:
        key = e.question.strip().lower()
        if key not in q_count:
            q_count[key] = {"question": e.question, "count": 0, "question_type": e.question_type}
        q_count[key]["count"] += 1
    top_q = sorted(q_count.values(), key=lambda x: x["count"], reverse=True)[:10]

    slide_counts: dict[str, int] = {}
    for e in entries:
        k = str(e.slide_index)
        slide_counts[k] = slide_counts.get(k, 0) + 1

    return {
        "total_questions": total,
        "deferred_count": deferred,
        "deferral_rate": round(deferred / total, 3),
        "faq_hit_count": faq_hits,
        "type_distribution": type_dist,
        "top_questions": top_q,
        "per_slide_counts": slide_counts,
    }


# ── EPIC 12 — S12.4 FAQ CRUD ─────────────────────────────────────────────────

def _faq_match_score(q1: str, q2: str) -> float:
    """Jaccard similarity on word tokens (minus stop words)."""
    _STOP = {"what", "is", "are", "the", "a", "an", "can", "do", "does", "how",
             "why", "when", "where", "who", "will", "would", "should", "could",
             "i", "you", "we", "they", "it", "this", "that", "about", "your"}

    def tokens(s: str) -> set[str]:
        words = re.sub(r"[^\w\s]", "", s.lower()).split()
        return {w for w in words if w not in _STOP and len(w) > 1}

    a, b = tokens(q1), tokens(q2)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _check_faq(project_id: str, question: str, db: Session) -> "FAQ | None":
    """Return the best matching approved FAQ, or None."""
    faqs = db.query(FAQ).filter(FAQ.project_id == project_id, FAQ.approved.is_(True)).all()
    best_score, best_faq = 0.0, None
    for faq in faqs:
        score = _faq_match_score(question, faq.question)
        if score > best_score:
            best_score, best_faq = score, faq
    if best_score >= 0.55:
        return best_faq
    return None


@router.get("/{project_id}/faq-candidates", response_model=list[FAQCandidateOut])
def get_faq_candidates(project_id: str, db: DbDep, min_occurrences: int = 2) -> list[dict]:
    """Return questions asked ≥ min_occurrences times that are not yet FAQ entries."""
    _get_project_or_404(project_id, db)
    existing_faq_qs = {
        faq.question.strip().lower()
        for faq in db.query(FAQ).filter(FAQ.project_id == project_id).all()
    }
    entries: list[QAEntry] = db.query(QAEntry).filter(QAEntry.project_id == project_id).all()

    # group by normalized question
    groups: dict[str, list[QAEntry]] = {}
    for e in entries:
        key = e.question.strip().lower()
        if key in existing_faq_qs:
            continue
        groups.setdefault(key, []).append(e)

    candidates = []
    for key, group in groups.items():
        if len(group) < min_occurrences:
            continue
        # best answer = highest confidence non-deferred answer
        best = max(group, key=lambda e: (not e.deferred, e.confidence))
        candidates.append({
            "question": best.question,
            "question_type": best.question_type,
            "answer_text": best.answer_text,
            "confidence": best.confidence,
            "occurrence_count": len(group),
        })

    return sorted(candidates, key=lambda c: c["occurrence_count"], reverse=True)


@router.get("/{project_id}/faqs", response_model=list[FAQOut])
def list_faqs(project_id: str, db: DbDep) -> list[FAQ]:
    _get_project_or_404(project_id, db)
    return db.query(FAQ).filter(FAQ.project_id == project_id).order_by(FAQ.created_at).all()


@router.post("/{project_id}/faqs", response_model=FAQOut, status_code=201)
def create_faq(project_id: str, body: CreateFAQRequest, db: DbDep) -> FAQ:
    _get_project_or_404(project_id, db)
    faq = FAQ(
        project_id=project_id,
        question=body.question,
        canonical_answer=body.canonical_answer,
        question_type=body.question_type,
        promoted_from_qa=body.promoted_from_qa,
        approved=False,
    )
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


@router.put("/{project_id}/faqs/{faq_id}", response_model=FAQOut)
def update_faq(project_id: str, faq_id: str, body: UpdateFAQRequest, db: DbDep) -> FAQ:
    _get_project_or_404(project_id, db)
    faq = db.get(FAQ, faq_id)
    if not faq or faq.project_id != project_id:
        raise HTTPException(404, "FAQ not found")
    if body.canonical_answer is not None:
        faq.canonical_answer = body.canonical_answer
    if body.question_type is not None:
        faq.question_type = body.question_type
    if body.approved is not None:
        faq.approved = body.approved
    db.commit()
    db.refresh(faq)
    return faq


@router.delete("/{project_id}/faqs/{faq_id}", status_code=204)
def delete_faq(project_id: str, faq_id: str, db: DbDep) -> None:
    _get_project_or_404(project_id, db)
    faq = db.get(FAQ, faq_id)
    if not faq or faq.project_id != project_id:
        raise HTTPException(404, "FAQ not found")
    db.delete(faq)
    db.commit()


@router.post("/{project_id}/faqs/{faq_id}/pre-bake", response_model=FAQOut)
def pre_bake_faq(
    project_id: str,
    faq_id: str,
    background_tasks: BackgroundTasks,
    db: DbDep,
) -> FAQ:
    project = _get_project_or_404(project_id, db)
    faq = db.get(FAQ, faq_id)
    if not faq or faq.project_id != project_id:
        raise HTTPException(404, "FAQ not found")
    if not faq.approved:
        raise HTTPException(400, "FAQ must be approved before pre-baking audio")

    settings = get_settings()
    faq_dir = os.path.join(settings.STORAGE_DIR, "projects", project.id, "faqs")
    os.makedirs(faq_dir, exist_ok=True)
    audio_path = os.path.join(faq_dir, f"faq_{faq.id}.wav")

    voice_id = (project.tone_profile or {}).get("voice_id")
    get_tts_provider().synthesize(faq.canonical_answer, audio_path, voice_id=voice_id)

    faq.pre_rendered_audio_path = audio_path
    db.commit()
    db.refresh(faq)
    return faq
