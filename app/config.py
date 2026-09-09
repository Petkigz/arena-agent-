from pathlib import Path
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
    BROWSER_TRANSFER_MAX_MB: int = 1024  # Owner-overridable local transfer safety quota
    BROWSER_DISK_SAFETY_MARGIN_MB: int = 512  # Free space kept unreserved beneath transfers
    ARENA_ASSOCIATIVE_MEMORY: str = "1"  # "0" disables vector-associative recall
    ARENA_BACKGROUND_OBSERVER: str = "1"  # "0" disables the read-only environment watcher
    ARENA_SCREEN_WATCHER: str = "1"  # "0" disables the desktop-awareness probe (screenshots stay local)
    ARENA_PARKED_RECHECK: str = "1"  # "0" disables automatic re-checks of parked goals
    ARENA_WORLD_FIRST: str = "1"  # "0" disables Phase-2 world-first briefs at the mind door
    ARENA_LEARNING_LOOP: str = "1"  # "0" disables Phase-6 experience learning at the mind door
    ARENA_TEACHING: str = "1"  # "0" disables Phase-7 conversational teaching ("watch this")
    ARENA_CURIOSITY: str = "1"  # "0" disables Phase-9 automatic UNKNOWN registration/resolution
    ARENA_IMAGINATION: str = "1"  # "0" disables Phase-10 automatic prediction-vs-reality comparison
    ARENA_PERCEPTION: str = "1"  # "0" disables Phase-13 perception intake at the mind door
    ARENA_ATTENTION: str = "1"  # "0" disables Phase-14 attention arbitration at the mind door
    ARENA_MOTIVATION: str = "1"  # "0" disables Phase-15 motivation refresh at the mind door
    ARENA_SOCIAL: str = "1"  # "0" disables Phase-16 owner-model pass at the mind door
    ARENA_PERSONALITY: str = "1"  # "0" disables Phase-17 personality evidence pass at the mind door
    ARENA_AUTHORITY: str = "1"  # "0" disables Phase-18 authority-rule extraction at the mind door
    ARENA_REFLECTION: str = "1"  # "0" disables Phase-19 reflection on verified cycles at the mind door
    ARENA_IMPROVEMENT: str = "1"  # "0" disables Phase-20 gap detection/proposals at the mind door
    ARENA_EVOLUTION: str = "1"  # "0" disables Phase-21 consolidation pass at the mind door
    ARENA_PRESENCE: str = "1"  # "0" disables Phase-22 presence-state settling at the mind door
    ARENA_EMBODIMENTS: str = "1"  # "0" disables Phase-23 presence broadcast to alive bodies at the mind door
    ARENA_EVALUATION: str = "1"  # "0" disables the Phase-24 generalization evaluation surface
    ARENA_AUTO_OPEN_DASHBOARD: str = "1"  # "0" stops the dashboard from opening when the server starts
    CODE_MODEL: str = "auto"  # pinned coder model id, or "auto" = best loaded code specialist
    ARENA_ANNOUNCEMENT_GUARD: str = "1"  # "0" disables the no-announcements reply guard
    ARENA_ELEVATED_ACKNOWLEDGED: str = "0"  # "1" = owner accepts elevated operation; warning becomes INFO
    ARENA_EMBEDDING_URL: str = ""  # LM Studio base URL for real embeddings (optional)
    ARENA_EMBEDDING_MODEL: str = ""  # e.g. text-embedding-nomic-embed-text-v1.5
    # Uncertainty questions (F1.2): low calibrated confidence asks the owner.
    ARENA_ASK_QUESTIONS_ENABLED: str = "1"  # "0" disables the uncertainty gate
    ARENA_ASK_CONFIDENCE_THRESHOLD: float = 0.45  # calibrated confidence floor
    ARENA_QUESTION_TTL_HOURS: int = 72  # unanswered questions expire honestly
    ARENA_WORKING_MEMORY_CAPACITY: int = 9  # F1.3 scratchpad capacity (~7±2)
    ARENA_MEMORY_SCAN_WINDOW: int = 1000  # lexical candidate window (raised with record caps)
    # Presentation-only age marker for retrieved history. Stale records remain
    # queryable and are never treated as current observations.
    ARENA_MEMORY_STALE_AFTER_HOURS: float = 720.0

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
