"""
VOXOPS AI Gateway — Agent Handoff Endpoints

POST /create-ticket
  Creates a support ticket when the AI system escalates
  an issue to a human agent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from configs.logging_config import get_logger
from src.voxops.database.db import get_db

log = get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# In-memory ticket store (will migrate to DB in Phase 7)
# ---------------------------------------------------------------------------

_tickets: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class TicketCreate(BaseModel):
    customer_id: str = Field(..., description="Customer identifier")
    issue_summary: str = Field(..., min_length=5, description="Brief description of the issue")
    transcript: str = Field(default="", description="Full conversation transcript")
    order_id: str | None = Field(default=None, description="Related order ID if applicable")
    priority: str = Field(default="normal", description="Ticket priority: low | normal | high | urgent")


class TicketOut(BaseModel):
    ticket_id: str
    customer_id: str
    issue_summary: str
    transcript: str
    order_id: str | None
    priority: str
    status: str
    created_at: str


# ---------------------------------------------------------------------------
# POST /create-ticket
# ---------------------------------------------------------------------------

@router.post("/create-ticket", response_model=TicketOut, status_code=201)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    """
    Create a support ticket for agent handoff.

    The AI system calls this when it determines a query requires
    human intervention (e.g. complaints, reroute requests).
    """
    valid_priorities = {"low", "normal", "high", "urgent"}
    if payload.priority not in valid_priorities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority '{payload.priority}'. Must be one of: {sorted(valid_priorities)}",
        )

    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    ticket = {
        "ticket_id": ticket_id,
        "customer_id": payload.customer_id,
        "issue_summary": payload.issue_summary,
        "transcript": payload.transcript,
        "order_id": payload.order_id,
        "priority": payload.priority,
        "status": "open",
        "created_at": now,
    }
    _tickets[ticket_id] = ticket

    log.info(
        "Ticket created: {} (customer={}, priority={}, order={})",
        ticket_id,
        payload.customer_id,
        payload.priority,
        payload.order_id,
    )
    return TicketOut(**ticket)


# ---------------------------------------------------------------------------
# GET /tickets  — list all tickets (utility endpoint)
# ---------------------------------------------------------------------------

@router.get("/tickets", response_model=list[TicketOut])
def list_tickets():
    """Return all support tickets (in-memory store)."""
    return [TicketOut(**t) for t in _tickets.values()]


# ---------------------------------------------------------------------------
# GET /tickets/{ticket_id}  — single ticket lookup
# ---------------------------------------------------------------------------

@router.get("/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str):
    """Look up a single ticket by ID."""
    ticket = _tickets.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found.")
    return TicketOut(**ticket)
