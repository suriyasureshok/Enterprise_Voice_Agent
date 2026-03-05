"""
VOXOPS AI Gateway — FastAPI Application

Initialises the FastAPI server, registers middleware, mounts API routers,
and runs database initialisation on startup.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from configs.settings import settings
from configs.logging_config import get_logger, setup_logging
from src.voxops.database.db import init_db, check_connection

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — runs on startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown hook."""
    setup_logging(settings.log_level, settings.log_file)
    log.info("VOXOPS AI Gateway starting  (env={})", settings.app_env)

    # Ensure DB tables exist
    init_db()
    if not check_connection():
        log.error("Database connection failed — aborting startup.")
        raise RuntimeError("Cannot connect to the database.")

    log.info("Database ready.")
    yield
    log.info("VOXOPS AI Gateway shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VOXOPS AI Gateway",
    description="Voice-based AI gateway with logistics simulation.",
    version="0.1.0",
    lifespan=lifespan,
    debug=settings.debug,
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------

from src.voxops.backend.api.routes_voice import router as voice_router       # noqa: E402
from src.voxops.backend.api.routes_orders import router as orders_router     # noqa: E402
from src.voxops.backend.api.routes_simulation import router as sim_router    # noqa: E402
from src.voxops.backend.api.routes_agent import router as agent_router       # noqa: E402

app.include_router(voice_router)
app.include_router(orders_router)
app.include_router(sim_router)
app.include_router(agent_router)


# ---------------------------------------------------------------------------
# Health-check root
# ---------------------------------------------------------------------------

@app.get("/", tags=["health"], include_in_schema=False)
async def root():
    """Redirect root to the new frontend."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app/", status_code=302)


@app.get("/health", tags=["health"])
async def health():
    """Readiness check — verifies database connectivity."""
    import time
    now = time.monotonic()
    # Cache health result for 30 seconds to avoid DB spam from polling
    if now - health._last_check < 30 and health._last_result is not None:
        return health._last_result
    db_ok = check_connection()
    health._last_result = {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "unreachable",
    }
    health._last_check = now
    return health._last_result

health._last_check = 0.0  # type: ignore[attr-defined]
health._last_result = None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Static files & Frontend Serving
# ---------------------------------------------------------------------------

import pathlib as _pathlib

_FRONTEND_DIR    = _pathlib.Path(__file__).resolve().parents[3] / "frontend"
_DASHBOARD_DIR   = _FRONTEND_DIR / "agent_dashboard"
_NEW_FRONTEND_DIR = _pathlib.Path(__file__).resolve().parents[3] / "front_new"
_TTS_OUTPUT_DIR  = _pathlib.Path(__file__).resolve().parents[3] / "data" / "tts_output"

# Ensure TTS output dir exists
_TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── TTS audio files served at /audio/<filename>.wav ──
app.mount("/audio", StaticFiles(directory=str(_TTS_OUTPUT_DIR)), name="audio")
log.info("TTS audio mounted at /audio (dir: {})", _TTS_OUTPUT_DIR)

# ── Agent Dashboard ──
# Served at /dashboard/ → dashboard.html; relative assets (dashboard.css, dashboard.js)
# resolve under /dashboard/ because we redirect /dashboard → /dashboard/
if _DASHBOARD_DIR.is_dir():
    @app.get("/dashboard", tags=["frontend"], include_in_schema=False)
    async def redirect_dashboard():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/dashboard/", status_code=301)

    @app.get("/dashboard/", tags=["frontend"], include_in_schema=False)
    async def serve_dashboard():
        return FileResponse(str(_DASHBOARD_DIR / "dashboard.html"))

    @app.get("/dashboard/{filepath:path}", tags=["frontend"], include_in_schema=False)
    async def dashboard_static(filepath: str):
        file = _DASHBOARD_DIR / filepath
        if file.is_file():
            return FileResponse(str(file))
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")

    log.info("Dashboard mounted at /dashboard/ (dir: {})", _DASHBOARD_DIR)
else:
    log.warning("Dashboard directory not found at {}", _DASHBOARD_DIR)


# ── New Frontend (front_new) served at /app/ ──
if _NEW_FRONTEND_DIR.is_dir():
    @app.get("/app", tags=["frontend"], include_in_schema=False)
    async def redirect_app():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/app/", status_code=301)

    @app.get("/app/", tags=["frontend"], include_in_schema=False)
    async def serve_app():
        return FileResponse(str(_NEW_FRONTEND_DIR / "index.html"))

    @app.get("/app/{filepath:path}", tags=["frontend"], include_in_schema=False)
    async def app_static(filepath: str):
        file = _NEW_FRONTEND_DIR / filepath
        if file.is_file():
            return FileResponse(str(file))
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")

    log.info("New frontend mounted at /app/ (dir: {})", _NEW_FRONTEND_DIR)
else:
    log.warning("New frontend directory not found at {}", _NEW_FRONTEND_DIR)


