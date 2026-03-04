"""
VOXOPS AI Gateway — SQLAlchemy ORM Models

Tables:
  - orders
  - warehouses
  - vehicles
  - routes
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.voxops.database.db import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class OrderStatus(str, PyEnum):
    pending    = "pending"
    in_transit = "in_transit"
    delivered  = "delivered"
    delayed    = "delayed"
    cancelled  = "cancelled"


class VehicleStatus(str, PyEnum):
    available = "available"
    on_route  = "on_route"
    maintenance = "maintenance"


class TrafficLevel(str, PyEnum):
    low    = "low"
    medium = "medium"
    high   = "high"


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class Order(Base):
    """
    Represents a customer shipment order.
    """
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("distance > 0", name="ck_orders_distance_positive"),
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_vehicle_id", "vehicle_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    origin: Mapped[str] = mapped_column(String(100), nullable=False)
    destination: Mapped[str] = mapped_column(String(100), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"), nullable=True
    )
    distance: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(OrderStatus, name="order_status"),
        default=OrderStatus.pending,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    # Relationship
    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="orders", lazy="select")

    def __repr__(self) -> str:
        return f"<Order {self.order_id} | {self.status} | {self.origin} → {self.destination}>"


# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------

class Warehouse(Base):
    """
    Represents a logistics warehouse / distribution centre.
    """
    __tablename__ = "warehouses"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_warehouses_capacity_positive"),
        CheckConstraint("current_load >= 0", name="ck_warehouses_load_non_negative"),
        CheckConstraint("current_load <= capacity", name="ck_warehouses_load_le_capacity"),
        Index("ix_warehouses_city", "city"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    current_load: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @property
    def utilisation_pct(self) -> float:
        """Warehouse utilisation as a percentage (0–100)."""
        return round(self.current_load / self.capacity * 100, 1) if self.capacity else 0.0

    @property
    def is_full(self) -> bool:
        return self.current_load >= self.capacity

    def __repr__(self) -> str:
        return f"<Warehouse {self.warehouse_id} | {self.city} | {self.current_load}/{self.capacity}>"


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

class Vehicle(Base):
    """
    Represents a delivery vehicle in the fleet.
    """
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("speed > 0", name="ck_vehicles_speed_positive"),
        Index("ix_vehicles_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    driver_name: Mapped[str] = mapped_column(String(100), nullable=False)
    speed: Mapped[float] = mapped_column(Float, nullable=False, comment="Average speed in km/h")
    status: Mapped[str] = mapped_column(
        Enum(VehicleStatus, name="vehicle_status"),
        default=VehicleStatus.available,
        nullable=False,
    )
    current_location: Mapped[str] = mapped_column(String(100), nullable=True)

    # Relationship
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="vehicle", lazy="select")

    def __repr__(self) -> str:
        return f"<Vehicle {self.vehicle_id} | {self.driver_name} | {self.status}>"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class Route(Base):
    """
    Represents a logistics route between two cities.
    """
    __tablename__ = "routes"
    __table_args__ = (
        CheckConstraint("distance > 0", name="ck_routes_distance_positive"),
        Index("ix_routes_origin_destination", "origin", "destination"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    origin: Mapped[str] = mapped_column(String(100), nullable=False)
    destination: Mapped[str] = mapped_column(String(100), nullable=False)
    distance: Mapped[float] = mapped_column(Float, nullable=False, comment="Distance in km")
    average_traffic: Mapped[str] = mapped_column(
        Enum(TrafficLevel, name="traffic_level"),
        default=TrafficLevel.medium,
        nullable=False,
    )

    @property
    def traffic_multiplier(self) -> float:
        """Speed reduction factor based on traffic level."""
        return {"low": 1.0, "medium": 0.80, "high": 0.55}.get(self.average_traffic, 0.80)

    def __repr__(self) -> str:
        return f"<Route {self.route_id} | {self.origin} → {self.destination} | {self.distance} km>"

