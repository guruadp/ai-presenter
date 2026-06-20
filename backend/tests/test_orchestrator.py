"""EPIC 10 tests — Orchestrator & State Machine.

Covers:
  S10.1  FSM transitions: IDLE→LOADING→READY→SPEAKING→…→ENDED
  S10.2  Typed command/event contracts over the EventBus
  S10.3  Gate-based Q&A: cursor saved, jump stack push/pop, resume
  S10.4  Q&A time budget: watchdog fires, auto-advance
"""

import asyncio

import pytest

from app.services.event_bus import Command, CommandType, Event, EventBus, EventType
from app.services.orchestrator import Cursor, OrchestratorSession, OrchestratorState


# ── Test helpers ──────────────────────────────────────────────────────────────

def make_manifest(num_slides: int = 2, segments_per_slide: int = 1) -> dict:
    slides = []
    for i in range(num_slides):
        slides.append({
            "slide_id": f"slide_{i + 1}",
            "position": i + 1,
            "image_path": f"slides/slide_{i + 1}.png",
            "segments": [
                {
                    "index": j,
                    "text": f"Slide {i + 1} segment {j + 1}.",
                    "audio_path": f"audio/slide_{i + 1}_seg_{j + 1}.wav",
                    "audio_duration_seconds": 5.0,
                }
                for j in range(segments_per_slide)
            ],
        })
    return {"schema_version": 1, "slides": slides}


async def collect(queue: "asyncio.Queue[Event]", count: int, timeout: float = 1.0) -> list[Event]:
    events = []
    for _ in range(count):
        events.append(await asyncio.wait_for(queue.get(), timeout=timeout))
    return events


async def drain(queue: "asyncio.Queue[Event]", pause: float = 0.15) -> list[Event]:
    """Collect all events until `pause` seconds of silence."""
    events = []
    try:
        while True:
            events.append(await asyncio.wait_for(queue.get(), timeout=pause))
    except asyncio.TimeoutError:
        pass
    return events


def _start(bus: EventBus, manifest: dict) -> OrchestratorSession:
    session = OrchestratorSession("test", bus)
    asyncio.create_task(session.run())
    return session


# ── S10.1: FSM basic playback ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_load_transitions_idle_to_ready():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s1", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    events = await collect(sub, 2)

    assert events[0].type == EventType.STATE_CHANGED
    assert events[0].payload["state"] == OrchestratorState.LOADING
    assert events[1].type == EventType.STATE_CHANGED
    assert events[1].payload["state"] == OrchestratorState.READY
    assert session.state == OrchestratorState.READY


@pytest.mark.asyncio
async def test_start_emits_play_slide_and_play_audio():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s2", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    await collect(sub, 2)  # LOADING + READY

    await bus.publish_command(Command(CommandType.START))
    events = await collect(sub, 3)  # SPEAKING + PLAY_SLIDE + PLAY_AUDIO

    types = {e.type for e in events}
    assert EventType.STATE_CHANGED in types
    assert EventType.PLAY_SLIDE in types
    assert EventType.PLAY_AUDIO in types

    state_ev = next(e for e in events if e.type == EventType.STATE_CHANGED)
    slide_ev = next(e for e in events if e.type == EventType.PLAY_SLIDE)
    audio_ev = next(e for e in events if e.type == EventType.PLAY_AUDIO)

    assert state_ev.payload["state"] == OrchestratorState.SPEAKING
    assert slide_ev.payload["slide_index"] == 0
    assert audio_ev.payload["slide_index"] == 0
    assert audio_ev.payload["segment_index"] == 0
    assert audio_ev.payload["context"] == "narration"
    assert session.state == OrchestratorState.SPEAKING


@pytest.mark.asyncio
async def test_multiple_segments_per_slide_plays_sequentially():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s3", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2, segments_per_slide=2)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    start_events = await collect(sub, 3)

    audio_ev = next(e for e in start_events if e.type == EventType.PLAY_AUDIO)
    assert audio_ev.payload["segment_index"] == 0

    # Complete segment 0 → should play segment 1 (no gate yet)
    await bus.publish_command(Command(CommandType.AUDIO_COMPLETE, {"sentence_index": 2}))
    next_events = await collect(sub, 1)

    audio_ev2 = next_events[0]
    assert audio_ev2.type == EventType.PLAY_AUDIO
    assert audio_ev2.payload["segment_index"] == 1
    assert session.state == OrchestratorState.SPEAKING
    assert session.cursor.segment_index == 1


@pytest.mark.asyncio
async def test_last_segment_of_slide_opens_qa_gate():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s4", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    await collect(sub, 3)

    await bus.publish_command(Command(CommandType.AUDIO_COMPLETE, {"sentence_index": 0}))
    events = await collect(sub, 2)  # STATE_CHANGED(QA_LISTENING) + QA_GATE_OPEN

    state_ev = next(e for e in events if e.type == EventType.STATE_CHANGED)
    gate_ev = next(e for e in events if e.type == EventType.QA_GATE_OPEN)

    assert state_ev.payload["state"] == OrchestratorState.QA_LISTENING
    assert "budget_remaining_seconds" in gate_ev.payload
    assert gate_ev.payload["budget_remaining_seconds"] > 0
    assert session.state == OrchestratorState.QA_LISTENING


@pytest.mark.asyncio
async def test_single_slide_show_ends_without_qa_gate():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s5", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(1)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    await collect(sub, 3)

    await bus.publish_command(Command(CommandType.AUDIO_COMPLETE, {"sentence_index": 0}))
    events = await collect(sub, 2)  # STATE_CHANGED(ENDED) + SHOW_ENDED

    types = {e.type for e in events}
    assert EventType.SHOW_ENDED in types
    state_ev = next(e for e in events if e.type == EventType.STATE_CHANGED)
    assert state_ev.payload["state"] == OrchestratorState.ENDED
    assert session.state == OrchestratorState.ENDED


@pytest.mark.asyncio
async def test_pause_and_resume():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s6", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    await collect(sub, 3)

    await bus.publish_command(Command(CommandType.PAUSE))
    pause_events = await collect(sub, 2)  # STATE_CHANGED(PAUSED) + STOP_AUDIO
    assert session.state == OrchestratorState.PAUSED
    assert any(e.type == EventType.STOP_AUDIO for e in pause_events)

    await bus.publish_command(Command(CommandType.RESUME))
    resume_events = await collect(sub, 2)  # STATE_CHANGED(SPEAKING) + PLAY_AUDIO
    assert session.state == OrchestratorState.SPEAKING
    assert any(e.type == EventType.PLAY_AUDIO for e in resume_events)


# ── S10.2: Bus contract — typed events carry required fields ──────────────────

@pytest.mark.asyncio
async def test_state_changed_event_always_includes_cursor():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s7", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    events = await collect(sub, 2)

    for ev in events:
        if ev.type == EventType.STATE_CHANGED:
            assert "state" in ev.payload
            assert "cursor" in ev.payload
            cursor = ev.payload["cursor"]
            assert "slide_index" in cursor
            assert "segment_index" in cursor
            assert "sentence_index" in cursor


@pytest.mark.asyncio
async def test_empty_manifest_transitions_to_error():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s8", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": {"slides": []}}))
    events = await drain(sub)

    states = [e.payload.get("state") for e in events if e.type == EventType.STATE_CHANGED]
    assert OrchestratorState.ERROR in states
    assert session.state == OrchestratorState.ERROR


# ── S10.3: Gate-based Q&A with cursor save/resume ─────────────────────────────

@pytest.mark.asyncio
async def test_gated_qa_full_flow():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s9", bus, qa_budget_seconds=30.0)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    await collect(sub, 3)

    # End of slide 0 → gate opens
    await bus.publish_command(Command(CommandType.AUDIO_COMPLETE, {"sentence_index": 0}))
    await collect(sub, 2)  # QA_LISTENING + QA_GATE_OPEN
    assert session.state == OrchestratorState.QA_LISTENING
    assert session.cursor.slide_index == 0

    # Press PTT → QA_PROCESSING
    await bus.publish_command(Command(CommandType.QA_TRIGGER))
    await collect(sub, 1)
    assert session.state == OrchestratorState.QA_PROCESSING

    # Answer ready → QA_ANSWERING + PLAY_AUDIO(qa_answer)
    await bus.publish_command(Command(CommandType.QA_ANSWER_READY, {
        "answer": "Here is the answer.",
        "question_type": "product-fact",
        "confidence": 0.9,
        "deferred": False,
    }))
    answer_events = await collect(sub, 2)  # STATE_CHANGED(QA_ANSWERING) + PLAY_AUDIO
    assert session.state == OrchestratorState.QA_ANSWERING
    qa_audio = next(e for e in answer_events if e.type == EventType.PLAY_AUDIO)
    assert qa_audio.payload["context"] == "qa_answer"
    assert qa_audio.payload["answer"] == "Here is the answer."

    # Answer audio done → reopen gate (budget not exhausted)
    await bus.publish_command(Command(CommandType.AUDIO_COMPLETE))
    reopen_events = await collect(sub, 2)  # STATE_CHANGED(QA_LISTENING) + QA_GATE_OPEN
    assert session.state == OrchestratorState.QA_LISTENING

    # Close gate manually → advance to slide 1
    await bus.publish_command(Command(CommandType.QA_CLOSE))
    close_events = await collect(sub, 3)  # QA_GATE_CLOSE + STATE_CHANGED(ADVANCING) + PLAY_SLIDE

    types = {e.type for e in close_events}
    assert EventType.QA_GATE_CLOSE in types
    assert EventType.PLAY_SLIDE in types
    assert session.state == OrchestratorState.ADVANCING

    play_slide_ev = next(e for e in close_events if e.type == EventType.PLAY_SLIDE)
    assert play_slide_ev.payload["slide_index"] == 1

    # Viewer confirms → SPEAKING on slide 1
    await bus.publish_command(Command(CommandType.SLIDE_ADVANCED))
    resume_events = await collect(sub, 2)  # STATE_CHANGED(SPEAKING) + PLAY_AUDIO
    assert session.state == OrchestratorState.SPEAKING
    assert session.cursor.slide_index == 1


# ── S10.3: Jump stack ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_jump_pushes_cursor_and_returns():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s10", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(3)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    await collect(sub, 3)

    assert session.cursor.slide_index == 0
    assert session.jump_stack_depth == 0

    # Jump to slide 2
    await bus.publish_command(Command(CommandType.JUMP, {"target_slide_index": 2}))
    jump_events = await collect(sub, 2)  # STATE_CHANGED(ADVANCING) + PLAY_SLIDE

    assert session.jump_stack_depth == 1
    assert session.state == OrchestratorState.ADVANCING
    play_ev = next(e for e in jump_events if e.type == EventType.PLAY_SLIDE)
    assert play_ev.payload["slide_index"] == 2

    await bus.publish_command(Command(CommandType.SLIDE_ADVANCED))
    await collect(sub, 2)
    assert session.cursor.slide_index == 2

    # Jump back
    await bus.publish_command(Command(CommandType.JUMP_RETURN))
    return_events = await collect(sub, 2)  # ADVANCING + PLAY_SLIDE(0)

    assert session.jump_stack_depth == 0
    back_slide_ev = next(e for e in return_events if e.type == EventType.PLAY_SLIDE)
    assert back_slide_ev.payload["slide_index"] == 0

    await bus.publish_command(Command(CommandType.SLIDE_ADVANCED))
    await collect(sub, 2)
    assert session.cursor.slide_index == 0
    assert session.state == OrchestratorState.SPEAKING


@pytest.mark.asyncio
async def test_jump_return_on_empty_stack_is_a_noop():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s11", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    await collect(sub, 3)

    assert session.jump_stack_depth == 0
    await bus.publish_command(Command(CommandType.JUMP_RETURN))
    # No event expected — should stay SPEAKING
    events = await drain(sub, pause=0.1)
    assert session.state == OrchestratorState.SPEAKING


@pytest.mark.asyncio
async def test_jump_out_of_range_is_a_noop():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s12", bus)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    await collect(sub, 3)

    await bus.publish_command(Command(CommandType.JUMP, {"target_slide_index": 99}))
    events = await drain(sub, pause=0.1)
    assert session.state == OrchestratorState.SPEAKING
    assert session.jump_stack_depth == 0


# ── S10.4: Q&A time budget ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qa_budget_expires_and_advances_slide():
    bus = EventBus()
    sub = bus.subscribe()
    session = OrchestratorSession("s13", bus, qa_budget_seconds=0.1)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    await collect(sub, 3)

    # End of slide 0 → gate opens, budget watchdog starts (0.1s)
    await bus.publish_command(Command(CommandType.AUDIO_COMPLETE, {"sentence_index": 0}))
    await collect(sub, 2)  # QA_LISTENING + QA_GATE_OPEN

    # Watchdog fires after 0.1s
    events = await drain(sub, pause=0.5)  # wait up to 0.5s for the events

    types = [e.type for e in events]
    assert EventType.QA_TIME_EXPIRED in types
    assert EventType.QA_GATE_CLOSE in types
    # After the last slide's QA gate: should be ADVANCING (towards slide 1)
    assert session.state in (OrchestratorState.ADVANCING, OrchestratorState.ENDED)


@pytest.mark.asyncio
async def test_qa_budget_cancelled_on_manual_close():
    bus = EventBus()
    sub = bus.subscribe()
    # Long budget — but close manually before it fires
    session = OrchestratorSession("s14", bus, qa_budget_seconds=60.0)
    asyncio.create_task(session.run())

    await bus.publish_command(Command(CommandType.LOAD, {"manifest": make_manifest(2)}))
    await collect(sub, 2)
    await bus.publish_command(Command(CommandType.START))
    await collect(sub, 3)

    await bus.publish_command(Command(CommandType.AUDIO_COMPLETE, {"sentence_index": 0}))
    await collect(sub, 2)

    await bus.publish_command(Command(CommandType.QA_CLOSE))
    close_events = await collect(sub, 3)  # QA_GATE_CLOSE + ADVANCING + PLAY_SLIDE

    types = {e.type for e in close_events}
    assert EventType.QA_GATE_CLOSE in types
    # No QA_TIME_EXPIRED should appear
    assert EventType.QA_TIME_EXPIRED not in types
    assert session.state == OrchestratorState.ADVANCING

    # Internal watchdog task should be None (was cancelled)
    assert session._qa_budget_task is None
