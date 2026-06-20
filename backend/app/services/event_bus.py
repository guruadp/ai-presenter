import asyncio
from dataclasses import dataclass, field
from enum import Enum


class CommandType(str, Enum):
    LOAD = "load"
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    ADVANCE = "advance"        # manual next-slide
    PREV = "prev"              # manual previous-slide
    JUMP = "jump"              # jump to slide by index, push cursor to stack
    JUMP_RETURN = "jump_return"  # pop cursor and resume
    QA_TRIGGER = "qa_trigger"    # push-to-talk pressed
    QA_CLOSE = "qa_close"        # presenter closes gate manually
    QA_ANSWER_READY = "qa_answer_ready"  # Q&A engine produced an answer
    AUDIO_COMPLETE = "audio_complete"    # audio playback finished a segment
    SLIDE_ADVANCED = "slide_advanced"    # viewer confirmed slide change
    QA_BUDGET_EXPIRED = "qa_budget_expired"  # internal watchdog fires


class EventType(str, Enum):
    STATE_CHANGED = "state_changed"
    PLAY_SLIDE = "play_slide"
    PLAY_AUDIO = "play_audio"
    STOP_AUDIO = "stop_audio"
    QA_GATE_OPEN = "qa_gate_open"
    QA_GATE_CLOSE = "qa_gate_close"
    QA_TIME_WARNING = "qa_time_warning"
    QA_TIME_EXPIRED = "qa_time_expired"
    SHOW_ENDED = "show_ended"
    ERROR = "error"


@dataclass
class Command:
    type: CommandType
    payload: dict = field(default_factory=dict)


@dataclass
class Event:
    type: EventType
    payload: dict = field(default_factory=dict)


class EventBus:
    """Transport-agnostic in-process pub/sub bus for V1.

    V2 replaces the internals with a ROS2/CycloneDDS transport without
    touching any component that uses the bus.
    """

    def __init__(self) -> None:
        self._command_queue: asyncio.Queue[Command] = asyncio.Queue()
        self._subscribers: list[asyncio.Queue[Event]] = []

    def subscribe(self) -> "asyncio.Queue[Event]":
        q: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "asyncio.Queue[Event]") -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def publish_command(self, cmd: Command) -> None:
        await self._command_queue.put(cmd)

    def publish_command_sync(self, cmd: Command) -> None:
        self._command_queue.put_nowait(cmd)

    async def next_command(self) -> Command:
        return await self._command_queue.get()

    async def broadcast(self, event: Event) -> None:
        for q in list(self._subscribers):
            await q.put(event)
