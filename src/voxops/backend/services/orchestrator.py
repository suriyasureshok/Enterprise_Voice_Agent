"""
VOXOPS AI Gateway — Orchestrator

Central pipeline that handles a user query end-to-end:

    Voice / Text Query
    → Intent Detection
    → Data Retrieval (DB + RAG)
    → Simulation (if needed)
    → Response Generation
    → Agent Handoff (if needed)

The ``process_query`` function is the single entry point used by the
voice endpoint (``routes_voice.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from src.voxops.backend.services.intent_parser import Intent, ParsedIntent, parse_intent
from src.voxops.backend.services.response_generator import generate_response
from src.voxops.backend.services.agent_handoff import create_handoff, HandoffResult
from src.voxops.database.models import Order, Route, Vehicle, Warehouse


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorResult:
    """Everything produced by the pipeline for one query."""
    transcript: str
    intent: str
    confidence: float
    entities: Dict[str, str] = field(default_factory=dict)
    response_text: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    handoff: Optional[HandoffResult] = None
    needs_escalation: bool = False


# ---------------------------------------------------------------------------
# Internal helpers — data retrieval
# ---------------------------------------------------------------------------

def _fetch_order(db: Session, order_id: str) -> Optional[Dict[str, Any]]:
    """Look up an order by business ID and return it as a dict."""
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if order is None:
        return None
    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "origin": order.origin,
        "destination": order.destination,
        "vehicle_id": order.vehicle_id,
        "distance": order.distance,
        "status": order.status,
        "created_at": str(order.created_at),
    }


def _run_simulation(db: Session, order_id: str) -> Optional[Dict[str, Any]]:
    """Run the SimPy delivery prediction for an order."""
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if order is None:
        return None

    # Fetch vehicle speed
    speed_kmh = 60.0
    if order.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == order.vehicle_id).first()
        if vehicle:
            speed_kmh = vehicle.speed

    # Fetch route traffic level
    route = (
        db.query(Route)
        .filter(Route.origin == order.origin, Route.destination == order.destination)
        .first()
    )
    traffic_level = route.average_traffic if route else "medium"

    # Fetch warehouse
    wh = db.query(Warehouse).filter(Warehouse.city == order.origin).first()
    wh_id = wh.warehouse_id if wh else "WH-DEFAULT"
    wh_cap = wh.capacity if wh else 1000
    wh_load = wh.current_load if wh else 0

    from src.voxops.simulation.delivery_predictor import predict_delivery as sim_predict

    result = sim_predict(
        distance_km=order.distance,
        speed_kmh=speed_kmh,
        traffic_level=traffic_level,
        warehouse_id=wh_id,
        warehouse_capacity=wh_cap,
        warehouse_load=wh_load,
    )

    return {
        "order_id": order.order_id,
        "total_hours": result.total_hours,
        "total_minutes": result.total_minutes,
        "delay_probability": result.delay_probability,
        "confidence": result.confidence,
        "summary": result.summary,
    }


def _retrieve_rag_context(query: str, top_k: int = 3) -> str:
    """Get relevant context from the RAG knowledge base (best-effort)."""
    try:
        from src.voxops.rag.retriever import Retriever

        retriever = Retriever.get_instance()
        # Auto-ingest if the store is empty
        if retriever.store_count() == 0:
            retriever.ingest_knowledge_base()
        return retriever.retrieve_context_string(query, top_k=top_k)
    except Exception as exc:
        logger.warning("RAG retrieval failed (non-fatal): {}", exc)
        return ""


# ---------------------------------------------------------------------------
# Intent → handler dispatch
# ---------------------------------------------------------------------------

_ESCALATION_INTENTS = {Intent.COMPLAINT, Intent.ESCALATION, Intent.REROUTE_REQUEST}


def _handle_shipment_status(
    parsed: ParsedIntent, db: Session, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Fetch order info for shipment status queries."""
    order_id = parsed.entities.get("order_id")
    if order_id:
        order = _fetch_order(db, order_id)
        data["order"] = order
        data["order_id"] = order_id
    else:
        data["order"] = None
        data["order_id"] = None
    return data


def _handle_delivery_prediction(
    parsed: ParsedIntent, db: Session, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Run simulation for delivery prediction queries."""
    order_id = parsed.entities.get("order_id")
    if order_id:
        prediction = _run_simulation(db, order_id)
        data["prediction"] = prediction
    else:
        data["prediction"] = None
    return data


def _handle_complaint(
    parsed: ParsedIntent, db: Session, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Fetch order context and enrich data for complaint."""
    order_id = parsed.entities.get("order_id")
    if order_id:
        data["order"] = _fetch_order(db, order_id)
    return data


def _handle_reroute(
    parsed: ParsedIntent, db: Session, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Fetch order context for reroute requests."""
    order_id = parsed.entities.get("order_id")
    if order_id:
        data["order"] = _fetch_order(db, order_id)
    return data


def _handle_faq(
    parsed: ParsedIntent, db: Session, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Retrieve RAG context for FAQ-like queries."""
    context = _retrieve_rag_context(parsed.raw_query)
    data["rag_context"] = context
    return data


def _handle_unknown(
    parsed: ParsedIntent, db: Session, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Fallback: try RAG retrieval for unrecognised queries."""
    context = _retrieve_rag_context(parsed.raw_query)
    data["rag_context"] = context
    return data


_INTENT_HANDLERS = {
    Intent.SHIPMENT_STATUS:     _handle_shipment_status,
    Intent.DELIVERY_PREDICTION: _handle_delivery_prediction,
    Intent.COMPLAINT:           _handle_complaint,
    Intent.REROUTE_REQUEST:     _handle_reroute,
    Intent.FAQ:                 _handle_faq,
    Intent.ESCALATION:          lambda p, d, data: data,  # escalation → handoff only
    Intent.GREETING:            lambda p, d, data: data,
    Intent.FAREWELL:            lambda p, d, data: data,
    Intent.UNKNOWN:             _handle_unknown,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_query(
    query: str,
    db: Session,
    customer_id: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> OrchestratorResult:
    """
    Process a user query through the full pipeline.

    Parameters
    ----------
    query : str
        User's natural-language text (post-STT).
    db : Session
        Active SQLAlchemy session.
    customer_id : str, optional
        Resolved customer ID (if known from session context).
    conversation_history : list[dict], optional
        Previous conversation messages for transcript storage.

    Returns
    -------
    OrchestratorResult
    """
    logger.info("Orchestrator processing: '{}'", query[:120])

    # 1. Intent detection
    parsed = parse_intent(query)

    # merge supplied customer_id into entities
    if customer_id and "customer_id" not in parsed.entities:
        parsed.entities["customer_id"] = customer_id

    # 2. Data retrieval (intent-specific)
    data: Dict[str, Any] = {}
    handler = _INTENT_HANDLERS.get(parsed.intent, _handle_unknown)
    data = handler(parsed, db, data)

    # 3. Agent handoff (if needed)
    handoff: Optional[HandoffResult] = None
    needs_escalation = parsed.intent in _ESCALATION_INTENTS

    if needs_escalation:
        messages = conversation_history or [{"role": "user", "text": query}]
        handoff = create_handoff(
            intent=parsed.intent.value,
            query=query,
            customer_id=parsed.entities.get("customer_id"),
            order_id=parsed.entities.get("order_id"),
            entities=parsed.entities,
            transcript_messages=messages,
        )
        data["ticket"] = {
            "ticket_id": handoff.ticket_id,
            "priority": handoff.priority,
            "status": handoff.status,
        }

    # 4. Response generation
    response_text = generate_response(parsed.intent.value, data)

    result = OrchestratorResult(
        transcript=query,
        intent=parsed.intent.value,
        confidence=parsed.confidence,
        entities=parsed.entities,
        response_text=response_text,
        data=data,
        handoff=handoff,
        needs_escalation=needs_escalation,
    )

    logger.info(
        "Orchestrator result: intent={} conf={:.2f} escalation={} response='{}'",
        result.intent,
        result.confidence,
        result.needs_escalation,
        result.response_text[:80],
    )
    return result
