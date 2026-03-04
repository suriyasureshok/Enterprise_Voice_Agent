"""
VOXOPS AI Gateway — Application Entry Point

Starts the FastAPI server with uvicorn.

Usage:
    python main.py
    # or
    uvicorn src.voxops.backend.main:app --reload
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn
from configs.settings import settings
from configs.logging_config import setup_logging


def main() -> None:
    """Initialise logging and launch the ASGI server."""
    setup_logging(settings.log_level, settings.log_file)

    uvicorn.run(
        "src.voxops.backend.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
