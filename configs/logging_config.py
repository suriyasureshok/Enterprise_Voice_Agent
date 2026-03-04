"""
VOXOPS AI Gateway — Logging Configuration
Configures loguru for structured, rotating file + coloured console logging.
"""

import sys
from pathlib import Path
from loguru import logger


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """
    Configure loguru logger for the application.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file:  Absolute path to the rotating log file.
                   If None, falls back to the value from settings.
    """
    # Remove the default loguru handler
    logger.remove()

    # --- Console handler (coloured, human-readable) ---
    logger.add(
        sys.stdout,
        level=log_level.upper(),
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        enqueue=True,
    )

    # --- File handler (JSON-structured, rotating) ---
    if log_file is None:
        from configs.settings import settings
        log_file = settings.log_file

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_path),
        level=log_level.upper(),
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        serialize=True,          # JSON lines format
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    logger.info(
        "Logging initialised | level={} | file={}",
        log_level.upper(),
        log_file,
    )


def get_logger(name: str):
    """
    Return a context-bound logger for a module.

    Usage:
        from configs.logging_config import get_logger
        log = get_logger(__name__)
        log.info("Hello from {}", __name__)
    """
    return logger.bind(module=name)
