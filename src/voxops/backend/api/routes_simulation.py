"""
VOXOPS AI Gateway — Simulation / Prediction Endpoints

GET /predict-delivery/{order_id}
  Runs a full SimPy-based logistics simulation (route + warehouse)
  and returns a delivery prediction.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from configs.logging_config import get_logger
from src.voxops.database.db import get_db
from src.voxops.database.models import Order, Route, Vehicle, Warehouse
from src.voxops.simulation.delivery_predictor import predict_delivery as sim_predict

log = get_logger(__name__)

router = APIRouter(prefix="/simulation", tags=["simulation"])


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class RouteDetail(BaseModel):
    distance_km: float
    base_speed_kmh: float
    traffic_level: str
    traffic_multiplier: float
    effective_speed_kmh: float
    travel_time_hours: float
    travel_time_minutes: float
    random_delay_hours: float
    total_time_hours: float
    total_time_minutes: float


class WarehouseDetail(BaseModel):
    warehouse_id: str
    capacity: int
    current_load: int
    utilisation_pct: float
    queue_position: int
    queue_wait_hours: float
    processing_hours: float
    total_warehouse_hours: float
    total_warehouse_minutes: float


class DeliveryPrediction(BaseModel):
    order_id: str
    origin: str
    destination: str
    vehicle_id: str | None
    route: RouteDetail
    warehouse: WarehouseDetail
    total_hours: float
    total_minutes: float
    delay_probability: float
    confidence: str
    summary: str


# ---------------------------------------------------------------------------
# GET /predict-delivery/{order_id}
# ---------------------------------------------------------------------------

@router.get("/predict-delivery/{order_id}", response_model=DeliveryPrediction)
def predict_delivery(order_id: str, db: Session = Depends(get_db)):
    """
    Full delivery prediction using SimPy simulation.

    Combines route travel time (with traffic & random delay) and
    warehouse processing time (queue + loading) into one estimate.
    """
    # --- Fetch order -------------------------------------------------------
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")

    # --- Fetch vehicle -----------------------------------------------------
    speed_kmh = 60.0  # fallback
    if order.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == order.vehicle_id).first()
        if vehicle:
            speed_kmh = vehicle.speed

    # --- Fetch route -------------------------------------------------------
    route = (
        db.query(Route)
        .filter(Route.origin == order.origin, Route.destination == order.destination)
        .first()
    )
    traffic_level = route.average_traffic if route else "medium"

    # --- Fetch origin warehouse (best match by city) -----------------------
    wh = db.query(Warehouse).filter(Warehouse.city == order.origin).first()
    wh_id = wh.warehouse_id if wh else "WH-DEFAULT"
    wh_cap = wh.capacity if wh else 1000
    wh_load = wh.current_load if wh else 0

    # --- Run simulation ----------------------------------------------------
    result = sim_predict(
        distance_km=order.distance,
        speed_kmh=speed_kmh,
        traffic_level=traffic_level,
        warehouse_id=wh_id,
        warehouse_capacity=wh_cap,
        warehouse_load=wh_load,
    )

    log.info(
        "Prediction for {}: {:.2f}h total, delay_prob={:.1%}",
        order_id, result.total_hours, result.delay_probability,
    )

    return DeliveryPrediction(
        order_id=order.order_id,
        origin=order.origin,
        destination=order.destination,
        vehicle_id=order.vehicle_id,
        route=RouteDetail(
            distance_km=result.route.distance_km,
            base_speed_kmh=result.route.base_speed_kmh,
            traffic_level=result.route.traffic_level,
            traffic_multiplier=result.route.traffic_multiplier,
            effective_speed_kmh=result.route.effective_speed_kmh,
            travel_time_hours=result.route.travel_time_hours,
            travel_time_minutes=result.route.travel_time_minutes,
            random_delay_hours=result.route.random_delay_hours,
            total_time_hours=result.route.total_time_hours,
            total_time_minutes=result.route.total_time_minutes,
        ),
        warehouse=WarehouseDetail(
            warehouse_id=result.warehouse.warehouse_id,
            capacity=result.warehouse.capacity,
            current_load=result.warehouse.current_load,
            utilisation_pct=result.warehouse.utilisation_pct,
            queue_position=result.warehouse.queue_position,
            queue_wait_hours=result.warehouse.queue_wait_hours,
            processing_hours=result.warehouse.processing_hours,
            total_warehouse_hours=result.warehouse.total_warehouse_hours,
            total_warehouse_minutes=result.warehouse.total_warehouse_minutes,
        ),
        total_hours=result.total_hours,
        total_minutes=result.total_minutes,
        delay_probability=result.delay_probability,
        confidence=result.confidence,
        summary=result.summary,
    )
