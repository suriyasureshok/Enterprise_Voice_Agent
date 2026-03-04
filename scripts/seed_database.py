"""Convenience entry-point: run from project root to seed the database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.voxops.database.seed_data import run_seed

if __name__ == "__main__":
    run_seed()
