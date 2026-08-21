import logging
import sys
from pathlib import Path
from app.config import settings


def _reconfigure_stdout_utf8() -> None:
    """Make console output tolerate non-ASCII (e.g. '→') on Windows.

    Windows consoles default to cp1252, which cannot encode characters like '→'
    (U+2192) used in log messages. Without this, a logging.StreamHandler raises
    UnicodeEncodeError on every such line (caught by logging, but noisy). This
    reconfigures stdout to UTF-8 with 'replace' so logging never crashes on a
    character. Best-effort: silently no-op if the stream doesn't support it.
    """
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    """To set up separate logs for general app logs vs audit logs."""
    _reconfigure_stdout_utf8()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Ensure log directory exists
    log_dir = settings.DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    handler = logging.FileHandler(log_dir / log_file)        
    handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    
    # Avoid duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        logger.addHandler(handler)
        logger.addHandler(console_handler)

    return logger

# General application logger
app_logger = setup_logger("app", "app.log")

# Security and action audit logger
audit_logger = setup_logger("audit", "audit.log")
