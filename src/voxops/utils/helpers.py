"""General utility helpers for VOXOPS."""

from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    """Create directory (and parents) if it doesn't exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a numeric value between min and max."""
    return max(min_val, min(max_val, value))
