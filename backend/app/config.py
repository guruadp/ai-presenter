from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Required — missing keys raise a ValidationError with the field name listed
    OPENAI_API_KEY: str

    # Optional with sensible defaults
    ELEVENLABS_API_KEY: str = ""
    DATABASE_URL: str = "sqlite:///./data/ednex.db"
    STORAGE_DIR: str = "./data/storage"
    CHROMA_DIR: str = "./data/chroma"
    LOG_LEVEL: str = "INFO"
    TTS_PROVIDER: str = "openai"  # openai | free-local
    OPENAI_TTS_MODEL: str = "gpt-4o-mini-tts"
    OPENAI_TTS_VOICE: str = "marin"
    OPENAI_TTS_TIMEOUT_SECONDS: float = 12.0
    OPENAI_TTS_MAX_RETRIES: int = 0

    # Unitree G1 robot integration — set ROBOT_ENABLED=true in .env to activate
    ROBOT_ENABLED: bool = False
    ROBOT_NETWORK_INTERFACE: str = "enp3s0"  # NIC connected to robot (run: ip link show)
    ROBOT_VOLUME: int = 50               # 0-100
    ROBOT_PCM_GAIN: float = 1.0           # software amplification (1.0=none, 2.0=double)


@lru_cache
def get_settings() -> Settings:
    return Settings()
