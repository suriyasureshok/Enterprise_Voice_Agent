"""
VOXOPS AI Gateway — Warehouse Processing Simulator

Models warehouse loading / dispatch queues using SimPy.
Simulates:
  - Queue wait time (other orders ahead)
  - Loading / processing time per order
  - Dispatch readiness
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

import simpy

from configs.logging_config import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class WarehouseSimulationResult:
    """Output of a single warehouse processing simulation."""
    warehouse_id: str
    capacity: int
    current_load: int
    utilisation_pct: float
    queue_position: int
    queue_wait_hours: float
    processing_hours: float
    total_warehouse_hours: float
    total_warehouse_minutes: float


# ---------------------------------------------------------------------------
# SimPy process
# ---------------------------------------------------------------------------

def _warehouse_process(
    env: simpy.Environment,
    dock: simpy.Resource,
    result: dict,
    processing_time: float,
):
    """SimPy generator: order waits for a dock, then is loaded."""
    arrival = env.now
    with dock.request() as req:
        yield req
        queue_wait = env.now - arrival
        yield env.timeout(processing_time)
    result["queue_wait"] = queue_wait
    result["processing"] = processing_time
    result["total"] = queue_wait + processing_time


def _filler_orders(
    env: simpy.Environment,
    dock: simpy.Resource,
    count: int,
    processing_range: tuple[float, float],
):
    """Fill the dock queue with *count* orders ahead of ours."""
    for _ in range(count):
        with dock.request() as req:
            yield req
            yield env.timeout(random.uniform(*processing_range))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def simulate_warehouse(
    warehouse_id: str = "WH-UNKNOWN",
    capacity: int = 1000,
    current_load: int = 0,
    num_docks: int = 2,
    orders_ahead: int = 3,
    processing_time_range: tuple[float, float] = (0.25, 1.0),
    seed: Optional[int] = None,
) -> WarehouseSimulationResult:
    """
    Simulate warehouse processing for one order.

    Args:
        warehouse_id:           Identifier for logging.
        capacity:               Max warehouse capacity.
        current_load:           Current stock level.
        num_docks:              Number of parallel loading docks.
        orders_ahead:           Orders already in queue ahead of this one.
        processing_time_range:  (min, max) hours per order processing.
        seed:                   Optional RNG seed.

    Returns:
        WarehouseSimulationResult with queue and processing times.
    """
    if seed is not None:
        random.seed(seed)

    utilisation = round(current_load / capacity * 100, 1) if capacity > 0 else 0.0

    # Scale orders_ahead by utilisation (busier warehouse → longer queue)
    effective_ahead = max(1, int(orders_ahead * (1 + utilisation / 100)))

    env = simpy.Environment()
    dock = simpy.Resource(env, capacity=num_docks)

    # Enqueue filler orders
    env.process(_filler_orders(env, dock, effective_ahead, processing_time_range))

    # Our target order
    result: dict = {}
    processing_time = random.uniform(*processing_time_range)
    env.process(_warehouse_process(env, dock, result, processing_time))

    env.run()

    sim = WarehouseSimulationResult(
        warehouse_id=warehouse_id,
        capacity=capacity,
        current_load=current_load,
        utilisation_pct=utilisation,
        queue_position=effective_ahead,
        queue_wait_hours=round(result["queue_wait"], 4),
        processing_hours=round(result["processing"], 4),
        total_warehouse_hours=round(result["total"], 4),
        total_warehouse_minutes=round(result["total"] * 60, 1),
    )

    log.debug(
        "Warehouse sim [{}]: queue={} orders, wait={:.2f}h, proc={:.2f}h, total={:.2f}h",
        warehouse_id, effective_ahead,
        sim.queue_wait_hours, sim.processing_hours, sim.total_warehouse_hours,
    )
    return sim
