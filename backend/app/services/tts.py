import math
import os
import shutil
import subprocess
import wave
from dataclasses import dataclass

from openai import OpenAI

from app.config import get_settings


@dataclass(frozen=True)
class TTSResult:
    path: str
    provider: str
    voice_id: str | None
    duration_seconds: float


class FreeLocalTTS:
    """Free, swappable TTS adapter.

    Uses common local TTS binaries if installed. In minimal dev environments,
    falls back to a generated WAV tone so packaging and loader validation still
    work without network access or paid vendors.
    """

    provider_name = "free-local"

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_id: str | None = None,
        preview_config: dict | None = None,
    ) -> TTSResult:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        preview_config = preview_config or {}
        provider = self._try_system_tts(text, output_path, voice_id, preview_config)
        if provider is None:
            provider = "dev-wav-placeholder"
            self._write_placeholder_wav(text, output_path)
        return TTSResult(
            path=output_path,
            provider=provider,
            voice_id=voice_id,
            duration_seconds=_wav_duration(output_path),
        )

    def _try_system_tts(
        self,
        text: str,
        output_path: str,
        voice_id: str | None,
        preview_config: dict,
    ) -> str | None:
        voice = voice_id or str(preview_config.get("voice_id") or "")
        if shutil.which("espeak-ng"):
            cmd = ["espeak-ng", "-w", output_path]
            if voice:
                cmd.extend(["-v", voice])
            cmd.append(text)
            return _run_tts_command(cmd, output_path, "espeak-ng")

        if shutil.which("espeak"):
            cmd = ["espeak", "-w", output_path]
            if voice:
                cmd.extend(["-v", voice])
            cmd.append(text)
            return _run_tts_command(cmd, output_path, "espeak")

        if shutil.which("pico2wave"):
            cmd = ["pico2wave", "-w", output_path, text]
            return _run_tts_command(cmd, output_path, "pico2wave")

        if shutil.which("text2wave"):
            cmd = ["text2wave", "-o", output_path]
            return _run_tts_command(cmd, output_path, "festival", input_text=text)

        return None

    def _write_placeholder_wav(self, text: str, output_path: str) -> None:
        sample_rate = 22050
        words = max(1, len(text.split()))
        duration = min(12.0, max(1.2, words / 2.6))
        total_samples = int(sample_rate * duration)
        amplitude = 9000

        with wave.open(output_path, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            frames = bytearray()
            for i in range(total_samples):
                t = i / sample_rate
                envelope = 0.5 + 0.5 * math.sin(2 * math.pi * 2.5 * t)
                value = int(amplitude * envelope * math.sin(2 * math.pi * 180 * t))
                frames.extend(value.to_bytes(2, byteorder="little", signed=True))
            wav.writeframes(bytes(frames))


class OpenAITTS:
    provider_name = "openai"

    def __init__(self, fallback=None):
        self.fallback = fallback or FreeLocalTTS()
        self._openai_unavailable = False

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_id: str | None = None,
        preview_config: dict | None = None,
    ) -> TTSResult:
        settings = get_settings()
        preview_config = preview_config or {}
        voice = _openai_voice(voice_id, preview_config, settings.OPENAI_TTS_VOICE)
        instructions = _openai_instructions(preview_config)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if self._openai_unavailable:
            return self.fallback.synthesize(text, output_path, voice_id=voice, preview_config=preview_config)

        try:
            client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.OPENAI_TTS_TIMEOUT_SECONDS,
                max_retries=settings.OPENAI_TTS_MAX_RETRIES,
            )
            with client.audio.speech.with_streaming_response.create(
                model=settings.OPENAI_TTS_MODEL,
                voice=voice,
                input=text,
                instructions=instructions,
                response_format="wav",
            ) as response:
                response.stream_to_file(output_path)
        except Exception:
            self._openai_unavailable = True
            return self.fallback.synthesize(text, output_path, voice_id=voice, preview_config=preview_config)

        return TTSResult(
            path=output_path,
            provider=f"openai:{settings.OPENAI_TTS_MODEL}",
            voice_id=voice,
            duration_seconds=_wav_duration(output_path),
        )


def get_tts_provider():
    provider = get_settings().TTS_PROVIDER.strip().lower()
    if provider == "openai":
        return OpenAITTS()
    return FreeLocalTTS()


def _openai_voice(
    voice_id: str | None,
    preview_config: dict,
    default_voice: str,
) -> str:
    candidate = str(voice_id or preview_config.get("voice_id") or default_voice or "marin").strip()
    return candidate or "marin"


def _openai_instructions(preview_config: dict) -> str:
    emphasis = str(preview_config.get("emphasis") or "balanced")
    pause_ms = str(preview_config.get("pause_ms") or "250")
    return (
        "Speak like a polished human presenter: warm, confident, clear, and natural. "
        f"Use {emphasis} emphasis, conversational pacing, and roughly {pause_ms}ms pauses at sentence breaks. "
        "Do not sound robotic or like you are reading bullets."
    )


def _run_tts_command(
    cmd: list[str],
    output_path: str,
    provider: str,
    input_text: str | None = None,
) -> str | None:
    try:
        subprocess.run(
            cmd,
            input=input_text,
            text=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
    except Exception:
        return None
    if os.path.exists(output_path) and os.path.getsize(output_path) > 44:
        return provider
    return None


def _wav_duration(path: str) -> float:
    """Return WAV duration in seconds.

    Streaming TTS providers (e.g. OpenAI) write WAV files whose RIFF data-size
    field is 0xFFFFFFFF, causing wave.getnframes() to return ~2^32-1 (≈89478 s
    at 24 kHz).  Fall back to measuring from the actual file size instead.
    """
    try:
        with wave.open(path, "rb") as wav:
            rate = wav.getframerate()
            if not rate:
                return 0.0
            reported = wav.getnframes()
            # 0xFFFFFFFF is the sentinel used by streaming WAVs
            if reported >= 0xFFFF0000:
                channels = wav.getnchannels()
                sampwidth = wav.getsampwidth()
                data_bytes = max(0, os.path.getsize(path) - 44)
                frames = data_bytes // (channels * sampwidth)
            else:
                frames = reported
            return round(frames / float(rate), 3)
    except Exception:
        return 0.0
