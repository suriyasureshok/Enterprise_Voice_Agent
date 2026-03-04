"""voxops.backend.api package — API route modules."""

from src.voxops.backend.api.routes_voice import router as voice_router        # noqa: F401
from src.voxops.backend.api.routes_orders import router as orders_router      # noqa: F401
from src.voxops.backend.api.routes_simulation import router as sim_router     # noqa: F401
from src.voxops.backend.api.routes_agent import router as agent_router        # noqa: F401
