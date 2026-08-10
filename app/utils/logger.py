import logging
import sys
from pathlib import Path
from app.config import settings

def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    """To set up separate logs for general app logs vs audit logs."""
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
