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
- Do NOT use <think> tags, reasoning blocks, or chain-of-thought.
- IMPORTANT: For FAQ / knowledge-base questions, answer ONLY the specific
  question the customer asked. Do NOT recite or summarize the entire context.
  Pick the single most relevant fact and reply concisely.
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
            # Send only the best-matching passage to the LLM, not the full dump
            best = data.get("rag_best_passage", "")
            if not best:
                best = data["rag_context"].split("\n\n---\n\n")[0]
                if best.startswith("[Source:"):
                    best = best.split("\n", 1)[-1].strip()
            data_summary["knowledge_base_excerpt"] = best[:500]
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
        # Strip <think>...</think> blocks (closed or unclosed) some models produce
        import re as _re
        response = _re.sub(r'<think>.*?</think>', '', response, flags=_re.DOTALL).strip()
        response = _re.sub(r'<think>.*', '', response, flags=_re.DOTALL).strip()
        # Strip surrounding quotes if the model included them
        response = response.strip('"').strip("'")
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
    # If no order_id was given, this is a general tracking question — use RAG
    if data.get("_fallback_to_faq"):
        return _fmt_faq(data)

    order = data.get("order")
    if not order:
        order_id = data.get("order_id", "")
        if order_id:
            return f"I'm sorry, I couldn't find an order with ID {order_id}. Please double-check and try again."
        return "Could you please provide your order ID so I can look up the status? For example, ORD-001."

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
    # If no order_id was given, this is a general question — use RAG
    if data.get("_fallback_to_faq"):
        return _fmt_faq(data)

    pred = data.get("prediction")
    if not pred:
        return "I'd be happy to predict a delivery time. Could you please provide the order ID?"

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


def _clean_rag_passage(raw: str, user_query: str = "") -> str:
    """Clean a raw RAG passage into a TTS-friendly response.

    - Strips document headers (e.g. 'VOXOPS LOGISTICS — ...')
    - Extracts just the A: answer if the chunk is a Q/A pair
    - Removes section numbering like '3. MISSING PACKAGES'
    - Handles mid-sentence starts from chunk overlap
    - Caps length at ~300 chars
    """
    import re

    text = raw.strip()
    if not text:
        return ""

    # Remove common doc headers — match known titles only to avoid eating Q: pairs
    text = re.sub(
        r"^VOXOPS LOGISTICS\s*[—–-]\s*"
        r"(?:FREQUENTLY\s+ASKED\s+QUESTIONS|COMPANY\s+POLICIES|[A-Z ]+)\s*",
        "", text, flags=re.IGNORECASE
    ).strip()

    # Also strip a standalone all-caps title line at the start
    text = re.sub(r"^[A-Z ]{10,}\n+", "", text).strip()

    # If the text contains Q:/A: pairs, find the most relevant answer
    qa_pairs = re.findall(r"Q:\s*(.+?)\nA:\s*(.+?)(?=\nQ:|\Z)", text, re.DOTALL)
    if qa_pairs:
        # Find the Q/A pair most relevant to the user query
        if user_query:
            query_words = set(user_query.lower().split())
            best_score, best_answer = -1, ""
            for q, a in qa_pairs:
                q_words = set(q.lower().split())
                overlap = len(query_words & q_words)
                if overlap > best_score:
                    best_score = overlap
                    best_answer = a.strip()
            if best_answer:
                return best_answer[:300]
        # Fallback: return first answer
        return qa_pairs[0][1].strip()[:300]

    # --- Company-policy style text ---

    # Strip ALL numbered section headers like '3. MISSING PACKAGES\n' or '4. DAMAGED GOODS'
    text = re.sub(r"\d+\.\s+[A-Z][A-Z /&-]+\s*\n?", "", text).strip()

    # Remove leading partial sentences (from chunk overlap):
    # if text doesn't start with uppercase letter, bullet, or dash
    if text and not text[0].isupper() and text[0] not in "-•*":
        # Find the end of the partial sentence and skip to next sentence
        m = re.search(r"[.!?]\s+([A-Z\-•*])", text)
        if m:
            text = text[m.start() + 2:].strip()
        else:
            # No clear sentence boundary — try to skip to first bullet
            m2 = re.search(r"\n\s*[-•*]", text)
            if m2:
                text = text[m2.start():].strip()

    # Clean up bullet dashes into prose
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Strip leading bullet (dash, asterisk, bullet point)
        line = re.sub(r"^[-•*]\s*", "", line).strip()
        if line:
            cleaned_lines.append(line)

    text = ". ".join(cleaned_lines)

    # Collapse multiple periods / spaces
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r"\s{2,}", " ", text)

    if len(text) > 300:
        text = text[:300].rsplit(" ", 1)[0] + "…"

    return text


# Maximum L2 distance from ChromaDB above which a passage is considered irrelevant
_RAG_RELEVANCE_THRESHOLD = 0.55


def _fmt_faq(data: Dict[str, Any]) -> str:
    # Check relevance first — if the best passage is too distant, don't use it
    distance = data.get("rag_best_distance", 0.0)
    if distance > _RAG_RELEVANCE_THRESHOLD:
        return (
            "I'm sorry, I don't have specific information about that in our knowledge base. "
            "Would you like me to connect you with a human agent?"
        )

    # Use the single best-matching passage (not the full RAG dump)
    best = data.get("rag_best_passage", "").strip()
    if not best:
        # Fallback to rag_context, but only the first passage
        full = data.get("rag_context", "")
        if full:
            best = full.split("\n\n---\n\n")[0]  # take first chunk only
            # Strip the "[Source: ...]" header if present
            if best.startswith("[Source:"):
                best = best.split("\n", 1)[-1].strip()
    if best:
        query = data.get("_user_query", "")
        return _clean_rag_passage(best, query)
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
    # Check relevance first
    distance = data.get("rag_best_distance", 0.0)
    if distance > _RAG_RELEVANCE_THRESHOLD:
        return (
            "I'm not sure I understood your request. You can ask me about "
            "shipment tracking, delivery predictions, or company policies. "
            "Would you like to try again?"
        )

    # Use best passage only — same logic as FAQ to avoid dumping everything
    best = data.get("rag_best_passage", "").strip()
    if not best:
        full = data.get("rag_context", "")
        if full:
            best = full.split("\n\n---\n\n")[0]
            if best.startswith("[Source:"):
                best = best.split("\n", 1)[-1].strip()
    if best:
        query = data.get("_user_query", "")
        cleaned = _clean_rag_passage(best, query)
        if cleaned:
            return f"Here's what I found: {cleaned}"
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
