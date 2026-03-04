"""
VOXOPS AI Gateway — Order Endpoints

GET  /orders/{order_id}   — look up a single order by business ID
GET  /orders              — list all orders (with optional status filter)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from configs.logging_config import get_logger
from src.voxops.database.db import get_db
from src.voxops.database.models import Order, OrderStatus

log = get_logger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class OrderOut(BaseModel):
    """Serialised order returned by the API."""
    order_id: str
    customer_id: str
    origin: str
    destination: str
    vehicle_id: str | None
    distance: float
    status: str
    created_at: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# GET /orders/{order_id}
# ---------------------------------------------------------------------------

@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: str, db: Session = Depends(get_db)):
    """Look up a single order by its business ID (e.g. ``ORD-001``)."""
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")
    log.info("Order lookup: {}", order_id)
    return OrderOut(
        order_id=order.order_id,
        customer_id=order.customer_id,
        origin=order.origin,
        destination=order.destination,
        vehicle_id=order.vehicle_id,
        distance=order.distance,
        status=order.status,
        created_at=str(order.created_at),
    )


# ---------------------------------------------------------------------------
# GET /orders
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[OrderOut])
def list_orders(
    status: Optional[str] = Query(None, description="Filter by order status"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Return all orders, optionally filtered by status."""
    query = db.query(Order)
    if status:
        # Validate status value
        valid_statuses = [s.value for s in OrderStatus]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Valid values: {valid_statuses}",
            )
        query = query.filter(Order.status == status)
    orders = query.limit(limit).all()
    log.info("Listed {} orders (filter={})", len(orders), status or "none")
    return [
        OrderOut(
            order_id=o.order_id,
            customer_id=o.customer_id,
            origin=o.origin,
            destination=o.destination,
            vehicle_id=o.vehicle_id,
            distance=o.distance,
            status=o.status,
            created_at=str(o.created_at),
        )
        for o in orders
    ]
