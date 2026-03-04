"""
VOXOPS AI Gateway — FastAPI Application

Initialises the FastAPI server, registers middleware, mounts API routers,
and runs database initialisation on startup.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/", tags=["health"])
async def root():
    """Simple liveness probe."""
    return {"status": "ok", "service": "voxops-ai-gateway", "version": "0.1.0"}


@app.get("/health", tags=["health"])
async def health():
    """Readiness check — verifies database connectivity."""
    db_ok = check_connection()
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "unreachable",
    }
