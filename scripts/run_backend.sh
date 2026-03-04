#!/usr/bin/env bash
# Start the VOXOPS FastAPI backend server
cd "$(dirname "$0")/.."
source .venv/bin/activate
uvicorn voxops.backend.main:app --host 0.0.0.0 --port 8000 --reload
