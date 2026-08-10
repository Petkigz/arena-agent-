import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings

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
    DEFAULT_TIMEOUT: float = 30.0

    class Config:
        env_prefix = "LPA_"  # Local Personal Assistant env variables prefix
        env_file = ".env"
        extra = "ignore"

# Ensure data directories exist
settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.USER_MANUAL_PATH.parent.mkdir(parents=True, exist_ok=True)
