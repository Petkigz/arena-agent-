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
    # Belt-and-braces: give the handler its OWN utf-8 stream built on the
    # raw buffer — immune to sys.stdout being replaced or being a wrapper
    # without .reconfigure() (observed under uvicorn --reload on Windows).
    import io as _io
    try:
        _buffer = getattr(sys.stdout, "buffer", None)
        _console_stream = (
            _io.TextIOWrapper(_buffer, encoding="utf-8", errors="replace", line_buffering=True)
            if _buffer is not None else sys.stdout
        )
    except Exception:
        _console_stream = sys.stdout
    console_handler = logging.StreamHandler(_console_stream)
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

def harden_all_console_handlers() -> None:
    """Make every StreamHandler in the process tolerate any character.

    Live lesson: our own handler was UTF-8-safe, but uvicorn attaches its own
    console handler to the ROOT logger with the cp1252 console stream — app
    log lines propagate there and crash with UnicodeEncodeError. Wrap every
    non-UTF8 stream handler (root and named loggers) once, at startup.
    """
    import io as _io

    def _wrap(stream):
        try:
            encoding = str(getattr(stream, "encoding", "") or "").lower()
            if encoding in ("utf-8", "utf8"):
                return stream
            buffer = getattr(stream, "buffer", None)
            if buffer is None:
                return stream
            return _io.TextIOWrapper(buffer, encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            return stream

    seen = set()
    for logger in [logging.root] + list(logging.Logger.manager.loggerDict.values()):
        handlers = getattr(logger, "handlers", None)
        if not handlers:
            continue
        for handler in handlers:
            if isinstance(handler, logging.StreamHandler) and id(handler) not in seen:
                seen.add(id(handler))
                try:
                    if not isinstance(handler, logging.FileHandler):
                        handler.stream = _wrap(handler.stream)
                except Exception:
                    pass
