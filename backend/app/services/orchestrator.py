"""EPIC 10 — Orchestrator & State Machine.

Single-writer design: OrchestratorSession is the ONLY component that mutates
runtime state.  All other components communicate through the EventBus:
  - Components send typed Commands to the Orchestrator.
  - The Orchestrator broadcasts typed Events back.

FSM:  IDLE → LOADING → READY → SPEAKING ⇄ ADVANCING → … → ENDED
      Q&A branch: SPEAKING → QA_LISTENING → QA_PROCESSING → QA_ANSWERING
                  → (budget left? QA_LISTENING : advance slide)
"""

import asyncio
import dataclasses
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.services.event_bus import Command, CommandType, Event, EventBus, EventType


# ── FSM states ────────────────────────────────────────────────────────────────

class OrchestratorState(str, Enum):
    IDLE = "IDLE"
    LOADING = "LOADING"
    READY = "READY"
    SPEAKING = "SPEAKING"
    ADVANCING = "ADVANCING"
    PAUSED = "PAUSED"
    QA_LISTENING = "QA_LISTENING"
    QA_PROCESSING = "QA_PROCESSING"
    QA_ANSWERING = "QA_ANSWERING"
    ENDED = "ENDED"
    ERROR = "ERROR"


# ── Cursor (playback position) ────────────────────────────────────────────────

@dataclass
class Cursor:
    slide_index: int = 0
    segment_index: int = 0
    sentence_index: int = 0  # fine-grained stop position within a segment

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ── Orchestrator ──────────────────────────────────────────────────────────────

class OrchestratorSession:
    """Single-threaded asyncio event loop that owns the FSM and the cursor.

    Only this object writes runtime state.  Callers enqueue Commands via the
    bus; the session broadcasts Events back so any subscriber (control panel,
    slide viewer, audio player) can react.
    """

    def __init__(
        self,
        session_id: str,
        bus: EventBus,
        qa_budget_seconds: float = 120.0,
    ) -> None:
        self.session_id = session_id
        self._bus = bus
        self._qa_budget_seconds = qa_budget_seconds

        self._state = OrchestratorState.IDLE
        self._manifest: dict = {}
        self._slides: list[dict] = []
        self._cursor = Cursor()
        self._jump_stack: list[Cursor] = []

        self._qa_gate_opened_at: float = 0.0
        self._qa_used_seconds: float = 0.0
        self._qa_budget_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

        self._running = False

    # ── Public read-only properties ───────────────────────────────────────────

    @property
    def state(self) -> OrchestratorState:
        return self._state

    @property
    def cursor(self) -> Cursor:
        return dataclasses.replace(self._cursor)

    @property
    def jump_stack_depth(self) -> int:
        return len(self._jump_stack)

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        self._running = True
        while self._running:
            cmd = await self._bus.next_command()
            await self._handle_command(cmd)

    # ── Command dispatch ──────────────────────────────────────────────────────

    async def _handle_command(self, cmd: Command) -> None:
        s = self._state
        t = cmd.type

        if t == CommandType.STOP:
            await self._do_stop()
            return

        if s == OrchestratorState.IDLE and t == CommandType.LOAD:
            await self._do_load(cmd.payload)
        elif s == OrchestratorState.READY and t == CommandType.START:
            await self._do_start()
        elif s == OrchestratorState.SPEAKING and t == CommandType.PAUSE:
            await self._do_pause()
        elif s == OrchestratorState.PAUSED and t == CommandType.RESUME:
            await self._do_resume()
        elif s == OrchestratorState.SPEAKING and t == CommandType.AUDIO_COMPLETE:
            await self._do_audio_complete_narration(cmd.payload)
        elif s == OrchestratorState.ADVANCING and t == CommandType.SLIDE_ADVANCED:
            await self._do_slide_advanced()
        elif s == OrchestratorState.SPEAKING and t == CommandType.QA_TRIGGER:
            await self._do_open_qa_gate()
        elif s == OrchestratorState.QA_LISTENING and t == CommandType.QA_TRIGGER:
            await self._do_qa_question_triggered()
        elif s == OrchestratorState.QA_PROCESSING and t == CommandType.QA_ANSWER_READY:
            await self._do_qa_answer_ready(cmd.payload)
        elif s == OrchestratorState.QA_ANSWERING and t == CommandType.AUDIO_COMPLETE:
            await self._do_audio_complete_answer()
        elif s in (
            OrchestratorState.QA_LISTENING,
            OrchestratorState.QA_PROCESSING,
        ) and t == CommandType.QA_CLOSE:
            await self._do_qa_close()
        elif s in (
            OrchestratorState.QA_LISTENING,
            OrchestratorState.QA_PROCESSING,
            OrchestratorState.QA_ANSWERING,
        ) and t == CommandType.QA_BUDGET_EXPIRED:
            await self._do_qa_budget_expired()
        elif s == OrchestratorState.SPEAKING and t == CommandType.ADVANCE:
            await self._do_manual_advance()
        elif s == OrchestratorState.SPEAKING and t == CommandType.PREV:
            await self._do_prev()
        elif s == OrchestratorState.SPEAKING and t == CommandType.JUMP:
            await self._do_jump(cmd.payload)
        elif s == OrchestratorState.SPEAKING and t == CommandType.JUMP_RETURN:
            await self._do_jump_return()
        # All other (state, command) pairs are silently ignored — invalid transitions.

    # ── Transitions ───────────────────────────────────────────────────────────

    async def _do_load(self, payload: dict) -> None:
        await self._set_state(OrchestratorState.LOADING)
        manifest = payload.get("manifest", {})
        self._manifest = manifest
        self._slides = manifest.get("slides", [])
        self._cursor = Cursor()
        self._jump_stack.clear()
        self._qa_used_seconds = 0.0
        if not self._slides:
            await self._set_state(OrchestratorState.ERROR)
            await self._bus.broadcast(Event(EventType.ERROR, {"message": "Show File has no slides"}))
            return
        await self._set_state(OrchestratorState.READY)

    async def _do_start(self) -> None:
        await self._set_state(OrchestratorState.SPEAKING)
        await self._emit_play_slide(self._cursor.slide_index)
        await self._emit_play_audio(self._cursor.slide_index, self._cursor.segment_index)

    async def _do_pause(self) -> None:
        await self._set_state(OrchestratorState.PAUSED)
        await self._bus.broadcast(Event(EventType.STOP_AUDIO, {
            "sentence_index": self._cursor.sentence_index,
        }))

    async def _do_resume(self) -> None:
        await self._set_state(OrchestratorState.SPEAKING)
        await self._emit_play_audio(self._cursor.slide_index, self._cursor.segment_index)

    async def _do_stop(self) -> None:
        self._cancel_qa_budget()
        await self._set_state(OrchestratorState.IDLE)
        await self._bus.broadcast(Event(EventType.STOP_AUDIO, {}))
        self._running = False

    async def _do_audio_complete_narration(self, payload: dict) -> None:
        self._cursor.sentence_index = int(payload.get("sentence_index", 0))
        slide = self._slides[self._cursor.slide_index]
        segments = slide.get("segments", [])
        next_seg = self._cursor.segment_index + 1

        if next_seg < len(segments):
            self._cursor.segment_index = next_seg
            self._cursor.sentence_index = 0
            await self._emit_play_audio(self._cursor.slide_index, self._cursor.segment_index)
        else:
            next_slide = self._cursor.slide_index + 1
            if next_slide < len(self._slides):
                await self._open_qa_gate()
            else:
                await self._set_state(OrchestratorState.ENDED)
                await self._bus.broadcast(Event(EventType.SHOW_ENDED, {
                    "cursor": self._cursor.to_dict(),
                }))

    async def _do_slide_advanced(self) -> None:
        await self._set_state(OrchestratorState.SPEAKING)
        await self._emit_play_audio(self._cursor.slide_index, self._cursor.segment_index)

    async def _do_open_qa_gate(self) -> None:
        """PTT pressed while SPEAKING — open gate immediately."""
        await self._open_qa_gate()

    async def _do_qa_question_triggered(self) -> None:
        self._cancel_qa_budget()
        await self._set_state(OrchestratorState.QA_PROCESSING)

    async def _do_qa_answer_ready(self, payload: dict) -> None:
        await self._set_state(OrchestratorState.QA_ANSWERING)
        await self._bus.broadcast(Event(EventType.PLAY_AUDIO, {
            "context": "qa_answer",
            "answer": payload.get("answer", ""),
            "question_type": payload.get("question_type", "general"),
            "confidence": payload.get("confidence", 1.0),
            "deferred": payload.get("deferred", False),
        }))

    async def _do_audio_complete_answer(self) -> None:
        elapsed = time.monotonic() - self._qa_gate_opened_at if self._qa_gate_opened_at else 0.0
        self._qa_used_seconds += elapsed
        remaining = self._qa_budget_seconds - self._qa_used_seconds

        if remaining > 0:
            self._qa_gate_opened_at = time.monotonic()
            await self._set_state(OrchestratorState.QA_LISTENING)
            await self._bus.broadcast(Event(EventType.QA_GATE_OPEN, {
                "cursor": self._cursor.to_dict(),
                "budget_remaining_seconds": remaining,
            }))
            self._start_qa_budget(remaining)
        else:
            await self._do_qa_close_advance()

    async def _do_qa_close(self) -> None:
        self._cancel_qa_budget()
        if self._qa_gate_opened_at:
            elapsed = time.monotonic() - self._qa_gate_opened_at
            self._qa_used_seconds += elapsed
        await self._do_qa_close_advance()

    async def _do_qa_budget_expired(self) -> None:
        self._qa_budget_task = None
        await self._bus.broadcast(Event(EventType.QA_TIME_EXPIRED, {
            "cursor": self._cursor.to_dict(),
            "used_seconds": self._qa_used_seconds,
        }))
        await self._do_qa_close_advance()

    async def _do_qa_close_advance(self) -> None:
        await self._bus.broadcast(Event(EventType.QA_GATE_CLOSE, {
            "cursor": self._cursor.to_dict(),
        }))
        next_slide = self._cursor.slide_index + 1
        if next_slide < len(self._slides):
            self._cursor = Cursor(slide_index=next_slide)
            await self._set_state(OrchestratorState.ADVANCING)
            await self._emit_play_slide(self._cursor.slide_index)
        else:
            await self._set_state(OrchestratorState.ENDED)
            await self._bus.broadcast(Event(EventType.SHOW_ENDED, {
                "cursor": self._cursor.to_dict(),
            }))

    async def _do_manual_advance(self) -> None:
        next_slide = self._cursor.slide_index + 1
        if next_slide < len(self._slides):
            self._cursor = Cursor(slide_index=next_slide)
            await self._set_state(OrchestratorState.ADVANCING)
            await self._emit_play_slide(self._cursor.slide_index)
        else:
            await self._set_state(OrchestratorState.ENDED)
            await self._bus.broadcast(Event(EventType.SHOW_ENDED, {}))

    async def _do_prev(self) -> None:
        prev_slide = max(0, self._cursor.slide_index - 1)
        self._cursor = Cursor(slide_index=prev_slide)
        await self._set_state(OrchestratorState.ADVANCING)
        await self._emit_play_slide(self._cursor.slide_index)

    async def _do_jump(self, payload: dict) -> None:
        target = int(payload.get("target_slide_index", 0))
        if target < 0 or target >= len(self._slides):
            return
        self._jump_stack.append(dataclasses.replace(self._cursor))
        self._cursor = Cursor(slide_index=target)
        await self._set_state(OrchestratorState.ADVANCING)
        await self._emit_play_slide(self._cursor.slide_index)

    async def _do_jump_return(self) -> None:
        if not self._jump_stack:
            return
        self._cursor = self._jump_stack.pop()
        await self._set_state(OrchestratorState.ADVANCING)
        await self._emit_play_slide(self._cursor.slide_index)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _open_qa_gate(self) -> None:
        self._qa_gate_opened_at = time.monotonic()
        remaining = self._qa_budget_seconds - self._qa_used_seconds
        await self._set_state(OrchestratorState.QA_LISTENING)
        await self._bus.broadcast(Event(EventType.QA_GATE_OPEN, {
            "cursor": self._cursor.to_dict(),
            "budget_remaining_seconds": max(0.0, remaining),
        }))
        if remaining > 0:
            self._start_qa_budget(remaining)

    async def _set_state(self, new_state: OrchestratorState) -> None:
        self._state = new_state
        await self._bus.broadcast(Event(EventType.STATE_CHANGED, {
            "state": new_state.value,
            "cursor": self._cursor.to_dict(),
        }))

    async def _emit_play_slide(self, slide_index: int) -> None:
        slide = self._slides[slide_index] if slide_index < len(self._slides) else {}
        await self._bus.broadcast(Event(EventType.PLAY_SLIDE, {
            "slide_index": slide_index,
            "slide_id": slide.get("slide_id", ""),
            "image_path": slide.get("image_path", ""),
            "position": slide.get("position", slide_index + 1),
        }))

    async def _emit_play_audio(self, slide_index: int, segment_index: int) -> None:
        slide = self._slides[slide_index] if slide_index < len(self._slides) else {}
        segments = slide.get("segments", [])
        segment = segments[segment_index] if segment_index < len(segments) else {}
        await self._bus.broadcast(Event(EventType.PLAY_AUDIO, {
            "context": "narration",
            "slide_index": slide_index,
            "segment_index": segment_index,
            "audio_path": segment.get("audio_path", ""),
            "text": segment.get("text", ""),
            "duration_seconds": segment.get("audio_duration_seconds", 0.0),
        }))

    def _start_qa_budget(self, remaining_seconds: float) -> None:
        self._cancel_qa_budget()
        self._qa_budget_task = asyncio.create_task(
            self._qa_budget_watchdog(remaining_seconds)
        )

    def _cancel_qa_budget(self) -> None:
        if self._qa_budget_task and not self._qa_budget_task.done():
            self._qa_budget_task.cancel()
        self._qa_budget_task = None

    async def _qa_budget_watchdog(self, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
            await self._bus.publish_command(Command(CommandType.QA_BUDGET_EXPIRED))
        except asyncio.CancelledError:
            pass


# ── Session registry (one per process for V1 single-tenant) ───────────────────

_sessions: dict[str, tuple["OrchestratorSession", EventBus, "asyncio.Task"]] = {}  # type: ignore[type-arg]


def get_bus(session_id: str) -> Optional[EventBus]:
    entry = _sessions.get(session_id)
    return entry[1] if entry else None


def get_session(session_id: str) -> Optional[OrchestratorSession]:
    entry = _sessions.get(session_id)
    return entry[0] if entry else None


async def launch_session(
    session_id: str,
    manifest: dict,
    qa_budget_seconds: float = 120.0,
) -> OrchestratorSession:
    bus = EventBus()
    session = OrchestratorSession(session_id, bus, qa_budget_seconds)
    task = asyncio.create_task(session.run())
    _sessions[session_id] = (session, bus, task)
    await bus.publish_command(Command(CommandType.LOAD, {"manifest": manifest}))
    deadline = time.monotonic() + 1.0
    while session.state in (OrchestratorState.IDLE, OrchestratorState.LOADING):
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(0.01)
    return session


async def terminate_session(session_id: str) -> None:
    entry = _sessions.pop(session_id, None)
    if not entry:
        return
    session, bus, task = entry
    await bus.publish_command(Command(CommandType.STOP))
    await asyncio.sleep(0)
    if not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
