"""
VOXOPS Health Check — verifies all Phase 1 & 2 modules.
Run from project root: python health_check.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PASS = "[PASS]"
FAIL = "[FAIL]"

results = []


def check(label, fn):
    try:
        fn()
        results.append((PASS, label))
        print(f"  {PASS}  {label}")
    except Exception as e:
        results.append((FAIL, label))
        print(f"  {FAIL}  {label}  →  {e}")


print()
print("=" * 60)
print("  VOXOPS Health Check")
print("=" * 60)

# ------------------------------------------------------------------
print("\n[Phase 1] Configuration")
# ------------------------------------------------------------------

def _settings_import():
    from configs.settings import settings
    assert settings.app_env == "development"
    assert "voxops.db" in settings.database_url
    assert settings.whisper_model_size == "base"
    assert settings.embedding_model_name == "all-MiniLM-L6-v2"

check("configs.settings — loads & validates", _settings_import)


def _logging_import():
    from configs.logging_config import setup_logging, get_logger
    setup_logging("WARNING")
    log = get_logger("health")
    log.warning("Logging OK")

check("configs.logging_config — setup_logging + get_logger", _logging_import)


def _dirs_exist():
    for d in ["data", "data/tts_output", "data/knowledge_base", "logs", "configs", "src/voxops"]:
        assert Path(d).exists(), f"Missing directory: {d}"

check("required directories exist", _dirs_exist)


def _env_example():
    assert Path(".env.example").exists()

check(".env.example present", _env_example)


def _gitignore():
    assert Path(".gitignore").exists()
    content = Path(".gitignore").read_text()
    assert ".env" in content
    assert "chroma_db" in content

check(".gitignore contains VOXOPS entries", _gitignore)

# ------------------------------------------------------------------
print("\n[Phase 2] Database Layer")
# ------------------------------------------------------------------

def _db_import():
    from src.voxops.database.db import engine, SessionLocal, Base, get_db, session_scope, init_db, check_connection
    assert engine is not None
    assert SessionLocal is not None

check("db.py — engine & session factory imports", _db_import)


def _db_connection():
    from src.voxops.database.db import check_connection
    assert check_connection(), "Cannot connect to database"

check("db.py — database connection reachable", _db_connection)


def _models_import():
    from src.voxops.database.models import Order, Warehouse, Vehicle, Route
    from src.voxops.database.models import OrderStatus, VehicleStatus, TrafficLevel
    # Verify enums
    assert OrderStatus.in_transit.value == "in_transit"
    assert VehicleStatus.on_route.value == "on_route"
    assert TrafficLevel.high.value == "high"

check("models.py — all models & enums import", _models_import)


def _tables_exist():
    from src.voxops.database.db import engine
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    for t in ["orders", "warehouses", "vehicles", "routes"]:
        assert t in tables, f"Table '{t}' not found in DB"

check("database tables exist (orders/warehouses/vehicles/routes)", _tables_exist)


def _row_counts():
    from src.voxops.database.db import session_scope
    from src.voxops.database.models import Order, Warehouse, Vehicle, Route
    with session_scope() as db:
        o = db.query(Order).count()
        w = db.query(Warehouse).count()
        v = db.query(Vehicle).count()
        r = db.query(Route).count()
    assert o == 8, f"Expected 8 orders, got {o}"
    assert w == 8, f"Expected 8 warehouses, got {w}"
    assert v == 8, f"Expected 8 vehicles, got {v}"
    assert r == 8, f"Expected 8 routes, got {r}"
    print(f"         orders={o}  warehouses={w}  vehicles={v}  routes={r}")

check("seeded data row counts correct (8 each)", _row_counts)


def _order_relationships():
    from src.voxops.database.db import session_scope
    from src.voxops.database.models import Order
    with session_scope() as db:
        order = db.query(Order).filter_by(order_id="ORD-001").first()
        assert order is not None
        assert order.origin == "New York"
        assert order.destination == "Boston"
        assert order.vehicle is not None, "FK relationship to Vehicle not loading"

check("ORM relationship: Order → Vehicle works", _order_relationships)


def _warehouse_properties():
    from src.voxops.database.db import session_scope
    from src.voxops.database.models import Warehouse
    with session_scope() as db:
        wh = db.query(Warehouse).filter_by(warehouse_id="WH-001").first()
        assert wh is not None
        assert 0 <= wh.utilisation_pct <= 100
        assert isinstance(wh.is_full, bool)

check("Warehouse.utilisation_pct and is_full properties", _warehouse_properties)


def _route_multiplier():
    from src.voxops.database.db import session_scope
    from src.voxops.database.models import Route
    with session_scope() as db:
        route = db.query(Route).filter_by(route_id="RT-003").first()  # high traffic
        assert route is not None
        assert route.traffic_multiplier == 0.55

check("Route.traffic_multiplier property (high=0.55)", _route_multiplier)


def _schema_sql_exists():
    assert Path("src/voxops/database/schema.sql").exists()
    content = Path("src/voxops/database/schema.sql").read_text()
    for kw in ["CREATE TABLE", "orders", "warehouses", "vehicles", "routes", "CREATE INDEX"]:
        assert kw in content, f"Missing '{kw}' in schema.sql"

check("schema.sql exists and contains all tables + indexes", _schema_sql_exists)


def _utils_import():
    from src.voxops.utils.helpers import ensure_dir, clamp
    from src.voxops.utils.logger import log
    assert clamp(150, 0, 100) == 100
    assert clamp(-5, 0, 100) == 0

check("utils.helpers — ensure_dir, clamp work", _utils_import)

# ------------------------------------------------------------------
print()
print("=" * 60)
passed = sum(1 for s, _ in results if s == PASS)
failed = sum(1 for s, _ in results if s == FAIL)
print(f"  Result: {passed} passed  |  {failed} failed  |  {len(results)} total")
print("=" * 60)
print()

if failed:
    sys.exit(1)
