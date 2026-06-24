import asyncio
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/robot", tags=["robot"])

DbDep = Annotated[Session, Depends(get_db)]


class RobotStatusResponse(BaseModel):
    enabled: bool


class PlayAudioRequest(BaseModel):
    project_id: str
    show_file_id: str
    audio_path: str


@router.get("/status", response_model=RobotStatusResponse)
def get_robot_status(request: Request) -> RobotStatusResponse:
    bridge = getattr(request.app.state, "robot_bridge", None)
    return RobotStatusResponse(enabled=bridge is not None)


@router.post("/play-audio")
async def play_audio(request: Request, body: PlayAudioRequest, db: DbDep) -> dict:
    bridge = getattr(request.app.state, "robot_bridge", None)
    if not bridge:
        raise HTTPException(503, "Robot not connected")

    from app.models.project import ShowFile

    show_file_item = db.query(ShowFile).filter(
        ShowFile.id == body.show_file_id,
        ShowFile.project_id == body.project_id,
    ).first()
    if not show_file_item:
        raise HTTPException(404, "Show file not found")

    show_dir = os.path.abspath(os.path.dirname(show_file_item.manifest_path))
    requested = os.path.abspath(os.path.join(show_dir, body.audio_path))
    if not requested.startswith(show_dir + os.sep):
        raise HTTPException(400, "Invalid audio path")
    if not os.path.exists(requested):
        raise HTTPException(404, "Audio file not found")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, bridge._stream_wav, requested)
    return {"ok": True}
