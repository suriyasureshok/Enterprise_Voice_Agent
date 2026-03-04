-- =============================================================
-- VOXOPS AI Gateway — Database Schema
-- Engine: SQLite (default) | PostgreSQL (production)
-- =============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- -------------------------------------------------------------
-- ENUM-like check tables (SQLite does not have native ENUMs)
-- -------------------------------------------------------------

-- -------------------------------------------------------------
-- vehicles
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vehicles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id       TEXT    NOT NULL UNIQUE,
    driver_name      TEXT    NOT NULL,
    speed            REAL    NOT NULL CHECK (speed > 0),      -- avg km/h
    status           TEXT    NOT NULL DEFAULT 'available'
                             CHECK (status IN ('available', 'on_route', 'maintenance')),
    current_location TEXT
);

CREATE INDEX IF NOT EXISTS ix_vehicles_status     ON vehicles (status);
CREATE INDEX IF NOT EXISTS ix_vehicles_vehicle_id ON vehicles (vehicle_id);

-- -------------------------------------------------------------
-- orders
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    order_id     TEXT     NOT NULL UNIQUE,
    customer_id  TEXT     NOT NULL,
    origin       TEXT     NOT NULL,
    destination  TEXT     NOT NULL,
    vehicle_id   TEXT     REFERENCES vehicles (vehicle_id) ON DELETE SET NULL,
    distance     REAL     NOT NULL CHECK (distance > 0),      -- km
    status       TEXT     NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'in_transit', 'delivered',
                                            'delayed', 'cancelled')),
    created_at   DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at   DATETIME
);

CREATE INDEX IF NOT EXISTS ix_orders_order_id    ON orders (order_id);
CREATE INDEX IF NOT EXISTS ix_orders_customer_id ON orders (customer_id);
CREATE INDEX IF NOT EXISTS ix_orders_status      ON orders (status);
CREATE INDEX IF NOT EXISTS ix_orders_vehicle_id  ON orders (vehicle_id);

-- -------------------------------------------------------------
-- warehouses
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warehouses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    warehouse_id  TEXT    NOT NULL UNIQUE,
    city          TEXT    NOT NULL,
    capacity      INTEGER NOT NULL CHECK (capacity > 0),
    current_load  INTEGER NOT NULL DEFAULT 0
                          CHECK (current_load >= 0)
                          CHECK (current_load <= capacity)
);

CREATE INDEX IF NOT EXISTS ix_warehouses_warehouse_id ON warehouses (warehouse_id);
CREATE INDEX IF NOT EXISTS ix_warehouses_city         ON warehouses (city);

-- -------------------------------------------------------------
-- routes
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id        TEXT    NOT NULL UNIQUE,
    origin          TEXT    NOT NULL,
    destination     TEXT    NOT NULL,
    distance        REAL    NOT NULL CHECK (distance > 0),    -- km
    average_traffic TEXT    NOT NULL DEFAULT 'medium'
                            CHECK (average_traffic IN ('low', 'medium', 'high'))
);

CREATE INDEX IF NOT EXISTS ix_routes_route_id           ON routes (route_id);
CREATE INDEX IF NOT EXISTS ix_routes_origin_destination ON routes (origin, destination);

