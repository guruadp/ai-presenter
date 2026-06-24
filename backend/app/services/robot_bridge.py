"""Unitree G1 robot bridge — routes presenter audio and events to the robot.

Activated when ROBOT_ENABLED=true in .env. On each presentation session:
  - attach(bus) subscribes to the session's event bus
  - Streams narration WAV to the G1 speaker via PlayStream
  - Controls the RGB LED strip to reflect presenter state
  - Fires gesture cues via LocoClient (e.g. WaveHand on slide advance)
  - Publishes AUDIO_COMPLETE back to the orchestrator after playback

When ROBOT_ENABLED=false (default) this module is never imported.
"""

import asyncio
import logging
import time

import numpy as np
from pydub import AudioSegment

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

from app.services.event_bus import Command, CommandType, EventBus, EventType

logger = logging.getLogger(__name__)

# ~1 second of audio at 16kHz mono 16-bit
_CHUNK_BYTES = 32_000


class RobotBridge:
    def __init__(self, interface: str, volume: int, gain: float) -> None:
        logger.info("RobotBridge: initializing DDS on interface %r", interface)
        ChannelFactoryInitialize(0, interface)

        self._audio = AudioClient()
        self._audio.SetTimeout(10.0)
        self._audio.Init()
        self._audio.SetVolume(volume)

        self._loco = LocoClient()
        self._loco.SetTimeout(10.0)
        self._loco.Init()

        self._gain = gain
        self._bus: EventBus | None = None
        self._queue: asyncio.Queue | None = None
        self._task: asyncio.Task | None = None
        logger.info("RobotBridge: ready (volume=%d, gain=%.1f)", volume, gain)

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def attach(self, bus: EventBus) -> None:
        """Subscribe to a presentation session's event bus."""
        self._bus = bus
        self._queue = bus.subscribe()
        self._task = asyncio.create_task(self._loop(), name="robot-bridge")
        logger.info("RobotBridge: attached to session bus")

    async def detach(self) -> None:
        """Unsubscribe from the current session and clean up."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._queue and self._bus:
            self._bus.unsubscribe(self._queue)
            self._queue = None
            self._bus = None
        try:
            self._audio.PlayStop("presenter")
            self._led(0, 0, 0)
        except Exception:
            pass
        logger.info("RobotBridge: detached")

    # ── Event loop ────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                match event.type:
                    case EventType.PLAY_AUDIO:
                        await self._handle_play_audio(event.payload)
                    case EventType.PLAY_SLIDE:
                        self._handle_play_slide(event.payload)
                    case EventType.QA_GATE_OPEN:
                        self._led(0, 0, 255)      # blue = listening
                    case EventType.QA_GATE_CLOSE:
                        self._led(0, 255, 0)      # green = speaking
                    case EventType.STOP_AUDIO:
                        self._audio.PlayStop("presenter")
                        self._led(0, 0, 0)
                    case EventType.SHOW_ENDED:
                        self._audio.PlayStop("presenter")
                        self._led(0, 0, 0)
                    case EventType.ERROR:
                        self._led(255, 0, 0)      # red = error
            except Exception:
                logger.exception("RobotBridge: unhandled error in event loop")

    # ── Audio ─────────────────────────────────────────────────────────────────

    async def _handle_play_audio(self, payload: dict) -> None:
        self._led(0, 255, 0)
        audio_path: str = payload.get("audio_path", "")
        duration: float = payload.get("duration_seconds", 0.0)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._stream_wav, audio_path)

        # Wait for the robot to finish playing, then signal the orchestrator
        await asyncio.sleep(max(0.0, duration - 0.3))
        if self._bus:
            await self._bus.publish_command(
                Command(type=CommandType.AUDIO_COMPLETE, payload={})
            )

    def _stream_wav(self, audio_path: str) -> None:
        try:
            audio = AudioSegment.from_wav(audio_path)
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

            samples = np.frombuffer(audio.raw_data, dtype=np.int16).astype(np.float32)
            samples = np.clip(samples * self._gain, -32768, 32767).astype(np.int16)
            pcm_bytes = samples.tobytes()

            stream_id = str(int(time.time() * 1000))
            offset = 0
            while offset < len(pcm_bytes):
                chunk = pcm_bytes[offset : offset + _CHUNK_BYTES]
                ret, _ = self._audio.PlayStream("presenter", stream_id, chunk)
                if ret != 0:
                    logger.warning("RobotBridge: PlayStream returned %d", ret)
                    break
                offset += _CHUNK_BYTES
                time.sleep(1.0)
        except Exception:
            logger.exception("RobotBridge: error streaming WAV %r", audio_path)

    # ── Gestures & LEDs ───────────────────────────────────────────────────────

    def _handle_play_slide(self, payload: dict) -> None:
        cue: str = payload.get("gesture_cue", "none") or "none"
        if cue == "wave":
            self._gesture_wave()

    def _gesture_wave(self) -> None:
        try:
            self._loco.WaveHand()
        except Exception:
            logger.debug("RobotBridge: WaveHand failed (ignored)")

    def _led(self, r: int, g: int, b: int) -> None:
        try:
            self._audio.LedControl(r, g, b)
        except Exception:
            logger.debug("RobotBridge: LedControl failed (ignored)")
