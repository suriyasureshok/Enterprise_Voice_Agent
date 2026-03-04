"""
VOXOPS AI Gateway — Demo Data Seeder

Loads CSV files from /data and populates the database.
Safe to re-run: existing rows identified by their natural key are skipped.

Usage (from project root)::

    python -m src.voxops.database.seed_data
    # or via the helper script:
    python scripts/seed_database.py
"""

import csv
import sys
from pathlib import Path

# Make sure project root is on PYTHONPATH when run directly
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from configs.logging_config import get_logger, setup_logging
from configs.settings import settings
from src.voxops.database.db import init_db, session_scope
from src.voxops.database.models import Order, OrderStatus, Route, TrafficLevel, Vehicle, VehicleStatus, Warehouse

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_csv(filename: str) -> list[dict]:
    path = settings.data_dir / filename
    if not path.exists():
        log.warning("CSV file not found: {}", path)
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Seeders
# ---------------------------------------------------------------------------

def seed_vehicles(db) -> int:
    """Seed demo vehicles (inline, not from CSV)."""
    demo = [
        {"vehicle_id": "VEH-01", "driver_name": "Alice Monroe",   "speed": 90.0,  "status": "on_route",   "current_location": "New York"},
        {"vehicle_id": "VEH-02", "driver_name": "Bob Tremblay",   "speed": 85.0,  "status": "available",  "current_location": "Chicago"},
        {"vehicle_id": "VEH-03", "driver_name": "Carmen Reyes",   "speed": 95.0,  "status": "on_route",   "current_location": "Los Angeles"},
        {"vehicle_id": "VEH-04", "driver_name": "David Kim",      "speed": 80.0,  "status": "on_route",   "current_location": "Houston"},
        {"vehicle_id": "VEH-05", "driver_name": "Elena Vasquez",  "speed": 75.0,  "status": "on_route",   "current_location": "Phoenix"},
        {"vehicle_id": "VEH-06", "driver_name": "Frank Osei",     "speed": 100.0, "status": "available",  "current_location": "Philadelphia"},
        {"vehicle_id": "VEH-07", "driver_name": "Grace Nakamura", "speed": 88.0,  "status": "on_route",   "current_location": "San Antonio"},
        {"vehicle_id": "VEH-08", "driver_name": "Henry Okafor",   "speed": 92.0,  "status": "available",  "current_location": "Seattle"},
    ]
    inserted = 0
    for row in demo:
        exists = db.query(Vehicle).filter_by(vehicle_id=row["vehicle_id"]).first()
        if not exists:
            db.add(Vehicle(
                vehicle_id=row["vehicle_id"],
                driver_name=row["driver_name"],
                speed=row["speed"],
                status=VehicleStatus(row["status"]),
                current_location=row["current_location"],
            ))
            inserted += 1
    db.flush()  # Ensure vehicle PKs are available before orders FK
    log.info("Vehicles seeded: {} new rows", inserted)
    return inserted


def seed_warehouses(db) -> int:
    rows = _load_csv("warehouses.csv")
    inserted = 0
    for row in rows:
        exists = db.query(Warehouse).filter_by(warehouse_id=row["warehouse_id"]).first()
        if not exists:
            db.add(Warehouse(
                warehouse_id=row["warehouse_id"],
                city=row["city"].strip(),
                capacity=int(row["capacity"]),
                current_load=int(row["current_load"]),
            ))
            inserted += 1
    log.info("Warehouses seeded: {} new rows", inserted)
    return inserted


def seed_routes(db) -> int:
    rows = _load_csv("routes.csv")
    inserted = 0
    for row in rows:
        exists = db.query(Route).filter_by(route_id=row["route_id"]).first()
        if not exists:
            db.add(Route(
                route_id=row["route_id"],
                origin=row["origin"].strip(),
                destination=row["destination"].strip(),
                distance=float(row["distance"]),
                average_traffic=TrafficLevel(row["average_traffic"].strip()),
            ))
            inserted += 1
    log.info("Routes seeded: {} new rows", inserted)
    return inserted


def seed_orders(db) -> int:
    rows = _load_csv("demo_orders.csv")
    inserted = 0
    for row in rows:
        exists = db.query(Order).filter_by(order_id=row["order_id"]).first()
        if not exists:
            db.add(Order(
                order_id=row["order_id"],
                customer_id=row["customer_id"].strip(),
                origin=row["origin"].strip(),
                destination=row["destination"].strip(),
                vehicle_id=row["vehicle_id"].strip() or None,
                distance=float(row["distance"]),
                status=OrderStatus(row["status"].strip()),
            ))
            inserted += 1
    log.info("Orders seeded: {} new rows", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_seed() -> None:
    setup_logging(settings.log_level)
    log.info("=== VOXOPS Demo Data Seeder ===")

    init_db()   # Creates tables if they don't exist

    with session_scope() as db:
        seed_vehicles(db)
        seed_warehouses(db)
        seed_routes(db)
        seed_orders(db)

    log.info("Seeding complete.")


if __name__ == "__main__":
    run_seed()
