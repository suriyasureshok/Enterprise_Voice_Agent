"""
VOXOPS AI Gateway — Delivery Predictor

Combines the route simulator and warehouse simulator to produce
a full delivery prediction including:
  - Route travel time (with traffic & random delay)
  - Warehouse processing time (queue + loading)
  - Total estimated delivery time
  - Probability-of-delay estimate
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from configs.logging_config import get_logger
from src.voxops.simulation.route_simulator import simulate_route, RouteSimulationResult
from src.voxops.simulation.warehouse_simulator import simulate_warehouse, WarehouseSimulationResult

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DeliveryPredictionResult:
    """Combined delivery prediction."""
    # Route leg
    route: RouteSimulationResult
    # Warehouse leg
    warehouse: WarehouseSimulationResult
    # Combined
    total_hours: float
    total_minutes: float
    delay_probability: float          # 0.0 – 1.0
    confidence: str                   # low / medium / high
    summary: str


# ---------------------------------------------------------------------------
# Delay-probability heuristic
# ---------------------------------------------------------------------------

def _estimate_delay_probability(
    traffic_level: str,
    utilisation_pct: float,
    total_hours: float,
) -> float:
    """
    Simple heuristic: higher traffic + higher warehouse utilisation +
    longer total time → higher chance of delay.
    """
    base = {"low": 0.05, "medium": 0.15, "high": 0.35}.get(traffic_level, 0.15)
    util_factor = utilisation_pct / 100 * 0.25       # max +0.25
    time_factor = min(total_hours / 48, 0.20)        # long trips add up to +0.20
    prob = min(base + util_factor + time_factor, 0.95)
    return round(prob, 3)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict_delivery(
    distance_km: float,
    speed_kmh: float,
    traffic_level: str = "medium",
    warehouse_id: str = "WH-UNKNOWN",
    warehouse_capacity: int = 1000,
    warehouse_load: int = 0,
    num_docks: int = 2,
    orders_ahead: int = 3,
    random_delay_range: tuple[float, float] = (0.0, 0.5),
    processing_time_range: tuple[float, float] = (0.25, 1.0),
    seed: Optional[int] = None,
) -> DeliveryPredictionResult:
    """
    Full delivery prediction combining route travel and warehouse processing.

    Args:
        distance_km / speed_kmh / traffic_level: Route parameters.
        warehouse_*: Warehouse parameters.
        num_docks / orders_ahead: Queue model inputs.
        random_delay_range: Random road-delay bounds (hours).
        processing_time_range: Per-order warehouse time bounds (hours).
        seed: Optional RNG seed for reproducibility.

    Returns:
        DeliveryPredictionResult with full breakdown.
    """
    route_result = simulate_route(
        distance_km=distance_km,
        speed_kmh=speed_kmh,
        traffic_level=traffic_level,
        random_delay_range=random_delay_range,
        seed=seed,
    )

    wh_result = simulate_warehouse(
        warehouse_id=warehouse_id,
        capacity=warehouse_capacity,
        current_load=warehouse_load,
        num_docks=num_docks,
        orders_ahead=orders_ahead,
        processing_time_range=processing_time_range,
        seed=seed,
    )

    total_h = round(route_result.total_time_hours + wh_result.total_warehouse_hours, 4)
    total_m = round(total_h * 60, 1)

    delay_prob = _estimate_delay_probability(
        traffic_level, wh_result.utilisation_pct, total_h,
    )

    # Confidence based on data completeness
    if speed_kmh > 0 and distance_km > 0:
        confidence = "high" if delay_prob < 0.20 else "medium"
    else:
        confidence = "low"

    summary = (
        f"Est. delivery: {total_h:.2f}h ({total_m:.0f}min). "
        f"Route: {route_result.total_time_hours:.2f}h "
        f"(travel {route_result.travel_time_hours:.2f}h + delay {route_result.random_delay_hours:.2f}h). "
        f"Warehouse [{warehouse_id}]: {wh_result.total_warehouse_hours:.2f}h "
        f"(queue {wh_result.queue_wait_hours:.2f}h + proc {wh_result.processing_hours:.2f}h). "
        f"Delay probability: {delay_prob:.0%}."
    )

    log.info(
        "Delivery prediction: {:.2f}h total, delay_prob={:.1%}, conf={}",
        total_h, delay_prob, confidence,
    )

    return DeliveryPredictionResult(
        route=route_result,
        warehouse=wh_result,
        total_hours=total_h,
        total_minutes=total_m,
        delay_probability=delay_prob,
        confidence=confidence,
        summary=summary,
    )
