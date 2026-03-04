"""
VOXOPS AI Gateway — Route Simulator

Simulates vehicle travel along a route using SimPy discrete-event simulation.
Incorporates distance, vehicle speed, and traffic conditions to compute
estimated travel time.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

import simpy

from configs.logging_config import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Traffic multiplier lookup
# ---------------------------------------------------------------------------

TRAFFIC_MULTIPLIERS: dict[str, float] = {
    "low":    1.00,   # full speed
    "medium": 0.80,   # 80 % of base speed
    "high":   0.55,   # 55 % of base speed
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RouteSimulationResult:
    """Holds the output of a single route simulation run."""
    distance_km: float
    base_speed_kmh: float
    traffic_level: str
    traffic_multiplier: float
    effective_speed_kmh: float
    travel_time_hours: float
    travel_time_minutes: float
    random_delay_hours: float = 0.0
    total_time_hours: float = 0.0
    total_time_minutes: float = 0.0


# ---------------------------------------------------------------------------
# SimPy process
# ---------------------------------------------------------------------------

def _travel_process(
    env: simpy.Environment,
    result: dict,
    distance_km: float,
    effective_speed: float,
    random_delay_range: tuple[float, float],
):
    """SimPy generator: vehicle travels, optionally delayed."""
    base_time = distance_km / effective_speed  # hours
    yield env.timeout(base_time)

    # Optional random delay (traffic jam, rest stop, etc.)
    delay = random.uniform(*random_delay_range)
    if delay > 0:
        yield env.timeout(delay)

    result["base_hours"] = base_time
    result["delay_hours"] = delay
    result["total_hours"] = base_time + delay


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def simulate_route(
    distance_km: float,
    speed_kmh: float,
    traffic_level: str = "medium",
    random_delay_range: tuple[float, float] = (0.0, 0.5),
    seed: Optional[int] = None,
) -> RouteSimulationResult:
    """
    Run a SimPy simulation for a single route.

    Args:
        distance_km:         Route distance in kilometres.
        speed_kmh:           Vehicle base speed in km/h.
        traffic_level:       One of ``low``, ``medium``, ``high``.
        random_delay_range:  (min, max) hours of random additional delay.
        seed:                Optional RNG seed for reproducibility.

    Returns:
        RouteSimulationResult with all timing details.
    """
    if seed is not None:
        random.seed(seed)

    traffic_mult = TRAFFIC_MULTIPLIERS.get(traffic_level, 0.80)
    effective_speed = speed_kmh * traffic_mult

    if effective_speed <= 0:
        raise ValueError(f"Effective speed must be > 0 (got {effective_speed}).")

    env = simpy.Environment()
    result: dict = {}
    env.process(_travel_process(env, result, distance_km, effective_speed, random_delay_range))
    env.run()

    base_hours = result["base_hours"]
    delay_hours = result["delay_hours"]
    total_hours = result["total_hours"]

    sim_result = RouteSimulationResult(
        distance_km=distance_km,
        base_speed_kmh=speed_kmh,
        traffic_level=traffic_level,
        traffic_multiplier=traffic_mult,
        effective_speed_kmh=round(effective_speed, 2),
        travel_time_hours=round(base_hours, 4),
        travel_time_minutes=round(base_hours * 60, 1),
        random_delay_hours=round(delay_hours, 4),
        total_time_hours=round(total_hours, 4),
        total_time_minutes=round(total_hours * 60, 1),
    )

    log.debug(
        "Route sim: {}km @ {}km/h (traffic={}) → {:.2f}h + {:.2f}h delay = {:.2f}h",
        distance_km, speed_kmh, traffic_level,
        base_hours, delay_hours, total_hours,
    )
    return sim_result
