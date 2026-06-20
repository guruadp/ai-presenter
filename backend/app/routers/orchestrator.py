"""REST + WebSocket API for the Orchestrator (EPIC 10).

Session lifecycle:
  POST   /orchestrator/sessions          — load a Show File, get session_id
  GET    /orchestrator/sessions/{id}     — read current state + cursor
  POST   /orchestrator/sessions/{id}/command — send a command
  DELETE /orchestrator/sessions/{id}     — stop + clean up
  WS     /orchestrator/sessions/{id}/events — real-time event stream
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import PresenterSession, Project, QAEntry, ShowFile
from app.schemas.project import LogQARequest, PresenterSessionOut, QAEntryOut
from app.services.event_bus import Command, CommandType
from app.services import orchestrator as orch_svc

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

DbDep = Annotated[Session, Depends(get_db)]

_BLOCKED_COMMANDS = {CommandType.QA_BUDGET_EXPIRED}


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    project_id: str
    show_file_id: str
    qa_budget_seconds: float = 120.0


class CreateSessionResponse(BaseModel):
    session_id: str
    state: str


class SessionStateResponse(BaseModel):
    session_id: str
    state: str
    cursor: dict
    jump_stack_depth: int


class SendCommandRequest(BaseModel):
    type: str
    payload: dict = {}


class SendCommandResponse(BaseModel):
    state: str
    cursor: dict


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_show_file(project_id: str, show_file_id: str, db: Session) -> "ShowFile":
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    sf = next((s for s in project.show_files if s.id == show_file_id), None)
    if not sf:
        raise HTTPException(404, "Show File not found")
    if sf.status != "ready":
        raise HTTPException(400, f"Show File status is '{sf.status}', expected 'ready'")
    return sf


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(body: CreateSessionRequest, db: DbDep) -> CreateSessionResponse:
    import uuid
    sf = _get_show_file(body.project_id, body.show_file_id, db)
    session_id = str(uuid.uuid4())
    session = await orch_svc.launch_session(
        session_id,
        manifest=sf.manifest,
        qa_budget_seconds=body.qa_budget_seconds,
    )
    # S12.3: persist the session record so Q&A history can be linked
    db.add(PresenterSession(
        id=session_id,
        project_id=body.project_id,
        show_file_id=body.show_file_id,
    ))
    db.commit()
    return CreateSessionResponse(session_id=session_id, state=session.state.value)


@router.get("/sessions/{session_id}", response_model=SessionStateResponse)
def get_session(session_id: str) -> SessionStateResponse:
    session = orch_svc.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return SessionStateResponse(
        session_id=session_id,
        state=session.state.value,
        cursor=session.cursor.to_dict(),
        jump_stack_depth=session.jump_stack_depth,
    )


@router.post("/sessions/{session_id}/command", response_model=SendCommandResponse)
async def send_command(session_id: str, body: SendCommandRequest) -> SendCommandResponse:
    session = orch_svc.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    try:
        cmd_type = CommandType(body.type)
    except ValueError:
        raise HTTPException(400, f"Unknown command type: {body.type!r}")

    if cmd_type in _BLOCKED_COMMANDS:
        raise HTTPException(400, f"Command '{body.type}' is internal and cannot be sent externally")

    bus = orch_svc.get_bus(session_id)
    if not bus:
        raise HTTPException(404, "Session bus not found")

    await bus.publish_command(Command(cmd_type, body.payload))
    await asyncio.sleep(0)  # yield so the orchestrator loop processes it
    return SendCommandResponse(state=session.state.value, cursor=session.cursor.to_dict())


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: DbDep) -> dict:
    session = orch_svc.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await orch_svc.terminate_session(session_id)
    # S12.3: mark session as ended
    ps = db.get(PresenterSession, session_id)
    if ps and ps.ended_at is None:
        from datetime import datetime, timezone
        ps.ended_at = datetime.now(timezone.utc)
        db.commit()
    return {"status": "stopped", "session_id": session_id}


@router.post("/sessions/{session_id}/qa-log", response_model=QAEntryOut, status_code=201)
def log_qa_entry(session_id: str, body: LogQARequest, db: DbDep) -> QAEntry:
    """Record a Q&A exchange that happened during an active session."""
    ps = db.get(PresenterSession, session_id)
    if not ps:
        raise HTTPException(404, "Session not found")
    entry = QAEntry(
        session_id=session_id,
        project_id=ps.project_id,
        question=body.question,
        answer_text=body.answer,
        question_type=body.question_type,
        confidence=body.confidence,
        deferred=body.deferred,
        slide_index=body.slide_index,
        served_from_faq=body.served_from_faq,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.websocket("/sessions/{session_id}/events")
async def events_ws(session_id: str, ws: WebSocket) -> None:
    bus = orch_svc.get_bus(session_id)
    if not bus:
        await ws.close(code=4004, reason="Session not found")
        return
    await ws.accept()
    queue = bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await ws.send_json({"type": event.type.value, "payload": event.payload})
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
