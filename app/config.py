import re as _re
from pathlib import Path
from pydantic_settings import BaseSettings, EnvSettingsSource, SettingsConfigDict


class _BareNameEnvSource(EnvSettingsSource):
    """Accept the DOCUMENTED bare env names beside the LPA_-prefixed ones.

    Audit 2026-09-09: the loader's ``env_prefix`` is ``LPA_``, so every
    documented switch name (``ARENA_PARKED_RECHECK=0``,
    ``MAIN_MODEL=auto``, ``AUTONOMY_MODE=off`` …) was silently ignored by
    the settings loader — while half the codebase's kill switches read
    ``os.environ`` directly under exactly those bare names. Two
    incompatible conventions lived in one repo, and owner-facing
    instructions using the bare names had no effect.

    Bare names now work for the ``ARENA_*`` switches and the
    model/autonomy knobs; GENERIC field names (``DEBUG``, ``DB_PATH``,
    ``APP_NAME`` …) deliberately stay prefixed-only so an unrelated
    machine env var can never hijack them. When both are set, the
    ``LPA_`` name wins (existing deployments keep their authority).
    """

    _BARE_ALLOWED = _re.compile(
        r"^(?:ARENA_.+|MAIN_MODEL|FAST_MODEL|CODE_MODEL.*|AUTONOMY_.+)$")

    def get_field_value(self, field, field_name):
        if not self._BARE_ALLOWED.match(field_name.upper()):
            return None, field_name, False
        return super().get_field_value(field, field_name)


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
    ARENA_PARKED_RECHECK: str = "0"  # "1" enables automatic re-checks of parked goals. Phase 0 (owner plan 2026-09-10): OFF by default until the typed event ledger (Phase 1) replaces chat replay; rechecks are owner-invoked until then.
    ARENA_APP_IDENTITY: str = "1"  # Phase 2 (owner plan 2026-09-10): persistent app-target resolution via the world model before the inventory/fuzzy fallback. "0" restores the pre-Phase-2 launch path exactly (fail-open either way).
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
    ARENA_SCRUTINY: str = "1"  # "0" disables the devil's-advocate pass on verified successes at the mind door
    ARENA_BELIEFS: str = "1"  # "0" disables the owner-belief capture pass at the mind door
    ARENA_IDLE_REPLAY: str = "1"  # "0" disables the dream-like consolidation pass at the mind door
    ARENA_IDLE_REPLAY_SECONDS: str = "1800"  # quiet gap after which the door runs an idle replay
    ARENA_STAKES: str = "1"  # "0" disables the stakes-based effort assessment pass at the mind door
    ARENA_PARADIGMS: str = "1"  # "0" disables the paradigm-shift pass at the mind door
    ARENA_PHYSICS: str = "1"  # "0" disables the intuitive-physics pass at the mind door
    ARENA_MORTALITY: str = "1"  # "0" disables the mortality organ (audit #26, opened at the owner's request)
    ARENA_AUTO_OPEN_DASHBOARD: str = "1"  # "0" stops the dashboard from opening when the server starts
    CODE_MODEL: str = "auto"  # pinned coder model id, or "auto" = best loaded code specialist
    CODE_MODEL_AUTOSWAP: str = "1"  # "0" disables on-demand load+eject of the coder (owner 2026-09-09)
    CODE_MODEL_TTL_S: int = 300  # server-side idle backstop: provider ejects the coder after N idle seconds
    CODE_MODEL_EJECT_AFTER_S: int = 60  # client-side eject N seconds after the last code-lane use
    CODE_MODEL_LOAD_TIMEOUT_S: int = 90  # how long to wait for an on-demand coder load to finish
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
    #   "off"        — no autonomous cycle is scheduled (Phase 0 default,
    #                  owner plan 2026-09-10: background autonomy stays off
    #                  until the typed event ledger lands in Phase 1).
    #   "supervised" — cycle runs, but Level-3 actions always require owner approval.
    #   "bounded"    — reserved for a future mode with explicit per-goal limits.
    #   "full"       — reserved; NOT currently implemented (no path grants full autonomy).
    AUTONOMY_MODE: str = "off"
    AUTONOMY_INTERVAL_SECONDS: int = 3600

    model_config = SettingsConfigDict(
        env_prefix="LPA_",
        env_file=".env",
        extra="ignore"
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings,
                                   env_settings, dotenv_settings,
                                   file_secret_settings):
        return (
            init_settings,
            env_settings,  # LPA_-prefixed names — existing authority
            _BareNameEnvSource(settings_cls, env_prefix=""),
            dotenv_settings,
            file_secret_settings,
        )

# Ensure data directories exist
settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.USER_MANUAL_PATH.parent.mkdir(parents=True, exist_ok=True)
