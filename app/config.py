import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App General Settings
    APP_NAME: str = "Local Personal Assistant"
    DEBUG: bool = True
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    DB_PATH: Path = DATA_DIR / "assistant.db"
    USER_MANUAL_PATH: Path = BASE_DIR / "memory" / "user_operating_manual.md"
    RULES_PATH: Path = BASE_DIR / "memory" / "rules.md"
    
    # LM Studio / Local LLM Settings
    LM_STUDIO_URL: str = "http://localhost:1234/v1"
    FAST_MODEL: str = "qwen2.5-3b-instruct"
    MAIN_MODEL: str = "qwen2.5-9b-instruct"
    DEFAULT_TIMEOUT: float = 180.0  # Extended timeout (3 mins) to allow LM Studio to auto-load models into VRAM

    # Autonomy policy (P1 fix): the autonomous cycle is opt-in, not always-on.
    #   "off"        — no autonomous cycle is scheduled.
    #   "supervised" — cycle runs, but Level-3 actions always require owner approval (default).
    #   "bounded"    — reserved for a future mode with explicit per-goal limits.
    #   "full"       — reserved; NOT currently implemented (no path grants full autonomy).
    AUTONOMY_MODE: str = "supervised"
    AUTONOMY_INTERVAL_SECONDS: int = 3600

    model_config = SettingsConfigDict(
        env_prefix="LPA_",
        env_file=".env",
        extra="ignore"
    )

# Ensure data directories exist
settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.USER_MANUAL_PATH.parent.mkdir(parents=True, exist_ok=True)
