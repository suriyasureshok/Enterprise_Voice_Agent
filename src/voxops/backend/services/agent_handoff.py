"""
VOXOPS AI Gateway — Agent Handoff Service

Summarises the customer issue, creates a support ticket via the agent
API, and stores a conversation transcript.  The orchestrator calls
``create_handoff`` when the intent warrants human intervention
(complaint, escalation, reroute_request, etc.).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# In-memory transcript store (mirrors routes_agent._tickets)
# ---------------------------------------------------------------------------

_transcripts: Dict[str, List[Dict[str, str]]] = {}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HandoffResult:
    """Returned by ``create_handoff``."""
    ticket_id: str
    customer_id: str
    issue_summary: str
    priority: str
    status: str
    created_at: str
    transcript_stored: bool = False


# ---------------------------------------------------------------------------
# Issue summarisation helpers
# ---------------------------------------------------------------------------

_PRIORITY_MAP = {
    "complaint":       "high",
    "escalation":      "high",
    "reroute_request": "normal",
    "faq":             "low",
    "unknown":         "normal",
}


def _determine_priority(intent: str, entities: Dict[str, str] | None = None) -> str:
    """Map intent to a ticket priority."""
    return _PRIORITY_MAP.get(intent, "normal")


def _summarise_issue(
    intent: str,
    query: str,
    entities: Dict[str, str] | None = None,
) -> str:
    """
    Build a short human-readable summary from the intent and query.
    """
    entities = entities or {}
    order_id = entities.get("order_id", "N/A")

    summaries = {
        "complaint": f"Customer complaint regarding order {order_id}. Original query: \"{query}\"",
        "escalation": f"Customer requested human agent. Query: \"{query}\"",
        "reroute_request": f"Customer requests rerouting for order {order_id}. Query: \"{query}\"",
    }
    return summaries.get(intent, f"Customer query requiring human review: \"{query}\"")


# ---------------------------------------------------------------------------
# Transcript helpers
# ---------------------------------------------------------------------------

def store_transcript(
    ticket_id: str,
    messages: List[Dict[str, str]],
) -> None:
    """
    Store a conversation transcript keyed by ticket ID.

    Each message is a dict with ``role`` (``user`` | ``system``) and ``text``.
    """
    _transcripts[ticket_id] = messages
    logger.info("Stored transcript for ticket {} ({} messages)", ticket_id, len(messages))


def get_transcript(ticket_id: str) -> List[Dict[str, str]]:
    """Retrieve a stored transcript (empty list if not found)."""
    return _transcripts.get(ticket_id, [])


def clear_transcripts() -> None:
    """Clear all stored transcripts (for testing)."""
    _transcripts.clear()


# ---------------------------------------------------------------------------
# Main handoff function
# ---------------------------------------------------------------------------

def create_handoff(
    intent: str,
    query: str,
    customer_id: Optional[str] = None,
    order_id: Optional[str] = None,
    entities: Optional[Dict[str, str]] = None,
    transcript_messages: Optional[List[Dict[str, str]]] = None,
) -> HandoffResult:
    """
    Create a support ticket and store the conversation transcript.

    This is a **service-layer** function called by the orchestrator.
    It mirrors the ticket store used by ``routes_agent.py`` so tickets
    created here also appear in the ``GET /agent/tickets`` endpoint.

    Parameters
    ----------
    intent : str
        Detected intent (e.g. "complaint", "escalation").
    query : str
        Original user query text.
    customer_id : str, optional
        Customer identifier (falls back to entity extraction).
    order_id : str, optional
        Related order ID (falls back to entity extraction).
    entities : dict, optional
        Extracted entities from intent parsing.
    transcript_messages : list[dict], optional
        Conversation history to attach to the ticket.

    Returns
    -------
    HandoffResult
    """
    entities = entities or {}
    customer_id = customer_id or entities.get("customer_id", "UNKNOWN")
    order_id = order_id or entities.get("order_id")

    # Build summary & priority
    summary = _summarise_issue(intent, query, entities)
    priority = _determine_priority(intent, entities)

    # Generate ticket ID
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    # Persist ticket in routes_agent's store so it's visible via API
    try:
        from src.voxops.backend.api.routes_agent import _tickets

        ticket_data = {
            "ticket_id": ticket_id,
            "customer_id": customer_id,
            "issue_summary": summary,
            "transcript": query,
            "order_id": order_id,
            "priority": priority,
            "status": "open",
            "created_at": now,
        }
        _tickets[ticket_id] = ticket_data
    except ImportError:
        logger.warning("routes_agent not available — ticket {} stored only in handoff service", ticket_id)

    # Store transcript
    transcript_stored = False
    if transcript_messages:
        store_transcript(ticket_id, transcript_messages)
        transcript_stored = True

    logger.info(
        "Handoff created: ticket={} customer={} priority={} order={}",
        ticket_id, customer_id, priority, order_id,
    )

    return HandoffResult(
        ticket_id=ticket_id,
        customer_id=customer_id,
        issue_summary=summary,
        priority=priority,
        status="open",
        created_at=now,
        transcript_stored=transcript_stored,
    )
