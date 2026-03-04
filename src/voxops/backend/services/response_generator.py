"""
VOXOPS AI Gateway — Response Generator

Converts structured system outputs (order data, simulation results,
RAG context, handoff confirmations) into natural-language text
suitable for TTS playback.

Strategy:
  1. OpenRouter LLM — generates a natural, contextual voice response when
     the API key is configured.  The structured data is injected as context.
  2. Template formatters — deterministic fallback for every intent.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# LLM-based response generation (OpenRouter)
# ---------------------------------------------------------------------------

_LLM_RESPONSE_SYSTEM = """\
You are VOXOPS, a professional logistics AI voice assistant.
Given the user's intent, data retrieved from our systems, and any relevant
context, generate a natural, concise voice response (1-3 sentences max).

Rules:
- Speak directly to the customer in a warm but professional tone.
- Never say "JSON" or mention internal field names.
- If escalation happened, mention the ticket ID and reassure the customer.
- If data is missing, politely apologise and ask for clarification.
- Output ONLY the spoken response text. No lists, no markdown.
"""


def _llm_generate_response(intent: str, data: Dict[str, Any], query: str = "") -> Optional[str]:
    """
    Ask the LLM to produce a natural voice response.
    Returns ``None`` on any failure so caller falls back to templates.
    """
    try:
        from src.voxops.utils.llm_client import complete, available

        if not available():
            return None

        # Build a concise user message with structured context
        context_parts = [f"Customer intent: {intent}"]
        if query:
            context_parts.append(f"Customer said: \"{query}\"")

        # Serialise key data fields in a readable way
        data_summary = {}
        if data.get("order"):
            o = data["order"]
            data_summary["order"] = {
                "id": o.get("order_id"),
                "status": o.get("status"),
                "from": o.get("origin"),
                "to": o.get("destination"),
            }
        if data.get("prediction"):
            p = data["prediction"]
            data_summary["prediction"] = {
                "order_id": p.get("order_id"),
                "eta_hours": round(p.get("total_hours", 0), 1),
                "delay_probability_pct": round(p.get("delay_probability", 0) * 100),
                "summary": p.get("summary", ""),
            }
        if data.get("ticket"):
            t = data["ticket"]
            data_summary["ticket"] = {
                "id": t.get("ticket_id"),
                "priority": t.get("priority"),
            }
        if data.get("rag_context"):
            data_summary["knowledge_base_excerpt"] = data["rag_context"][:400]
        if data.get("order_id") and not data_summary.get("order"):
            data_summary["searched_order_id"] = data["order_id"]
            data_summary["order_found"] = False

        if data_summary:
            context_parts.append("System data: " + json.dumps(data_summary, default=str))

        user_msg = "\n".join(context_parts)

        response = complete(
            system_prompt=_LLM_RESPONSE_SYSTEM,
            user_message=user_msg,
            temperature=0.4,
            max_tokens=180,
        )
        # Strip surrounding quotes if the model included them
        response = response.strip().strip('"').strip("'")
        if response:
            logger.debug("[LLM] Response: '{}'...", response[:100])
            return response
        return None

    except Exception as exc:
        logger.warning("LLM response generation failed (using template fallback): {}", exc)
        return None


# ---------------------------------------------------------------------------
# Formatters — one per intent
# ---------------------------------------------------------------------------

def _fmt_shipment_status(data: Dict[str, Any]) -> str:
    order = data.get("order")
    if not order:
        order_id = data.get("order_id", "your order")
        return f"I'm sorry, I couldn't find an order with ID {order_id}. Please double-check and try again."

    oid = order.get("order_id", "unknown")
    status = order.get("status", "unknown")
    origin = order.get("origin", "")
    dest = order.get("destination", "")

    status_text = {
        "pending":    "currently pending and has not been dispatched yet",
        "in_transit": f"in transit from {origin} to {dest}",
        "delivered":  f"delivered to {dest}",
        "delayed":    f"currently delayed on its route from {origin} to {dest}",
        "cancelled":  "cancelled",
    }.get(status, f"in status '{status}'")

    return f"Order {oid} is {status_text}."


def _fmt_delivery_prediction(data: Dict[str, Any]) -> str:
    pred = data.get("prediction")
    if not pred:
        return "I'm sorry, I couldn't generate a delivery prediction for that order."

    oid = pred.get("order_id", "your order")
    total_h = pred.get("total_hours", 0)
    delay_prob = pred.get("delay_probability", 0)
    summary = pred.get("summary", "")

    if summary:
        return summary

    hours = int(total_h)
    minutes = int((total_h - hours) * 60)

    time_str = f"{hours} hour{'s' if hours != 1 else ''}"
    if minutes > 0:
        time_str += f" and {minutes} minute{'s' if minutes != 1 else ''}"

    delay_pct = f"{delay_prob * 100:.0f}%"
    return (
        f"The estimated delivery time for order {oid} is approximately {time_str}, "
        f"with a {delay_pct} probability of delay."
    )


def _fmt_complaint(data: Dict[str, Any]) -> str:
    ticket = data.get("ticket")
    if ticket:
        tid = ticket.get("ticket_id", "")
        return (
            f"I've created support ticket {tid} for your complaint. "
            "A human agent will review your case within 2 business hours."
        )
    return (
        "I understand your concern. Let me create a support ticket so our "
        "team can investigate. Could you provide your order ID?"
    )


def _fmt_reroute(data: Dict[str, Any]) -> str:
    order = data.get("order")
    if order:
        status = order.get("status", "")
        if status in ("delivered", "cancelled"):
            return f"Unfortunately, order {order.get('order_id')} has already been {status} and cannot be rerouted."
        if status == "in_transit":
            return (
                f"Order {order.get('order_id')} is already in transit. "
                "Post-dispatch rerouting may incur up to a $25 fee. "
                "I'll escalate this to an agent for processing."
            )
    return "To process a reroute request, please provide the order ID and the new delivery address."


def _fmt_faq(data: Dict[str, Any]) -> str:
    context = data.get("rag_context", "")
    if context:
        return f"Based on our knowledge base: {context}"
    return "I don't have specific information about that. Would you like me to connect you with an agent?"


def _fmt_escalation(data: Dict[str, Any]) -> str:
    ticket = data.get("ticket")
    if ticket:
        tid = ticket.get("ticket_id", "")
        return f"I've escalated your request. A human agent will be with you shortly. Your ticket ID is {tid}."
    return "I'm transferring you to a human agent now. Please hold for a moment."


def _fmt_greeting(_: Dict[str, Any]) -> str:
    return "Hello! I'm the VOXOPS logistics assistant. How can I help you today?"


def _fmt_farewell(_: Dict[str, Any]) -> str:
    return "Thank you for contacting VOXOPS. Have a great day!"


def _fmt_unknown(data: Dict[str, Any]) -> str:
    context = data.get("rag_context", "")
    if context:
        return f"Here's what I found that may help: {context}"
    return (
        "I'm not sure I understood your request. You can ask me about "
        "shipment tracking, delivery predictions, or company policies. "
        "Would you like to try again?"
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_FORMATTERS = {
    "shipment_status":     _fmt_shipment_status,
    "delivery_prediction": _fmt_delivery_prediction,
    "complaint":           _fmt_complaint,
    "reroute_request":     _fmt_reroute,
    "faq":                 _fmt_faq,
    "escalation":          _fmt_escalation,
    "greeting":            _fmt_greeting,
    "farewell":            _fmt_farewell,
    "unknown":             _fmt_unknown,
}


def generate_response(intent: str, data: Dict[str, Any] | None = None, query: str = "") -> str:
    """
    Generate a natural-language response for a given intent and data payload.

    Pipeline:
      1. Try OpenRouter LLM for a rich, contextual voice response.
      2. Fall back to deterministic template formatters.

    Parameters
    ----------
    intent : str
        Detected intent string (matches ``Intent`` enum values).
    data : dict
        Structured data from the orchestrator (order info, prediction, ticket, etc.).
    query : str, optional
        Original user query for LLM context.

    Returns
    -------
    str
        TTS-ready natural-language response.
    """
    data = data or {}

    # --- LLM primary ---
    llm_response = _llm_generate_response(intent, data, query)
    if llm_response:
        return llm_response

    # --- Template fallback ---
    formatter = _FORMATTERS.get(intent, _fmt_unknown)
    response = formatter(data)
    logger.debug("[Template] Response for intent '{}': {}…", intent, response[:120])
    return response
