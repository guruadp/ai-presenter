from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import FAQ, Project
from app.routers.projects import _faq_match_score
from app.services import qa as qa_svc

router = APIRouter(prefix="/projects", tags=["qa"])

DbDep = Annotated[Session, Depends(get_db)]


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


class TranscribeResponse(BaseModel):
    question: str
    is_empty: bool


class AnswerRequest(BaseModel):
    question: str
    slide_context: Optional[str] = None
    session_id: str = ""


class AnswerResponse(BaseModel):
    answer: str
    question_type: str
    citations: list[dict]
    confidence: float
    deferred: bool
    deferred_reason: Optional[str] = None


@router.post(
    "/{project_id}/show-files/{show_file_id}/qa/transcribe",
    response_model=TranscribeResponse,
)
async def transcribe_question(
    project_id: str,
    show_file_id: str,
    audio: UploadFile = File(...),
    db: DbDep = ...,  # type: ignore[assignment]
) -> TranscribeResponse:
    project = _get_project_or_404(project_id, db)
    if not any(sf.id == show_file_id for sf in project.show_files):
        raise HTTPException(404, "Show File not found")

    audio_bytes = await audio.read()
    result = qa_svc.transcribe_audio(audio_bytes, filename=audio.filename or "audio.webm")
    return TranscribeResponse(question=result.question, is_empty=result.is_empty)


@router.post(
    "/{project_id}/show-files/{show_file_id}/qa/answer",
    response_model=AnswerResponse,
)
def answer_question(
    project_id: str,
    show_file_id: str,
    body: AnswerRequest,
    db: DbDep,
) -> AnswerResponse:
    project = _get_project_or_404(project_id, db)
    sf = next((sf for sf in project.show_files if sf.id == show_file_id), None)
    if not sf:
        raise HTTPException(404, "Show File not found")

    # S12.4: Check approved FAQs before calling the LLM
    faqs = db.query(FAQ).filter(FAQ.project_id == project_id, FAQ.approved.is_(True)).all()
    best_score, best_faq = 0.0, None
    for faq in faqs:
        score = _faq_match_score(body.question, faq.question)
        if score > best_score:
            best_score, best_faq = score, faq
    if best_faq and best_score >= 0.55:
        best_faq.hit_count += 1
        db.commit()
        return AnswerResponse(
            answer=best_faq.canonical_answer,
            question_type=best_faq.question_type,
            citations=[],
            confidence=1.0,
            deferred=False,
            deferred_reason=None,
        )

    kb_ids = [kb.kb_id for kb in project.knowledge_bases]
    result = qa_svc.answer_question(
        question=body.question,
        kb_ids=kb_ids,
        slide_context=body.slide_context,
        project_id=project_id,
        session_id=body.session_id,
    )
    return AnswerResponse(
        answer=result.answer,
        question_type=result.question_type,
        citations=result.citations,
        confidence=result.confidence,
        deferred=result.deferred,
        deferred_reason=result.deferred_reason,
    )
