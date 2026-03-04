"""
VOXOPS AI Gateway — Intent Parser

Parses natural-language user queries to extract:
  - intent  (shipment_status, delivery_prediction, complaint, reroute_request,
              faq, greeting, farewell, escalation, unknown)
  - entities (order_id, customer_id, city names, etc.)

The parser uses keyword / regex heuristics so it works offline without an
LLM and is fully deterministic and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# Intents
# ---------------------------------------------------------------------------

class Intent(str, Enum):
    SHIPMENT_STATUS      = "shipment_status"
    DELIVERY_PREDICTION  = "delivery_prediction"
    COMPLAINT            = "complaint"
    REROUTE_REQUEST      = "reroute_request"
    FAQ                  = "faq"
    GREETING             = "greeting"
    FAREWELL             = "farewell"
    ESCALATION           = "escalation"
    UNKNOWN              = "unknown"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ParsedIntent:
    """Output of intent parsing."""
    intent: Intent
    confidence: float                                # 0.0 – 1.0
    entities: Dict[str, str] = field(default_factory=dict)
    raw_query: str = ""


# ---------------------------------------------------------------------------
# Pattern tables
# ---------------------------------------------------------------------------

# Each entry: (compiled regex, Intent, base confidence)
_INTENT_PATTERNS: List[Tuple[re.Pattern, Intent, float]] = []


def _p(pattern: str, intent: Intent, confidence: float = 0.85) -> None:
    """Helper — register a pattern."""
    _INTENT_PATTERNS.append((re.compile(pattern, re.IGNORECASE), intent, confidence))


# --- Shipment status -------------------------------------------------------
_p(r"\b(where\s+is|track|status|locate|find)\b.*\b(order|shipment|package|parcel)\b", Intent.SHIPMENT_STATUS, 0.92)
_p(r"\b(order|shipment|package|parcel)\b.*\b(status|where|track|locate)\b",           Intent.SHIPMENT_STATUS, 0.90)
_p(r"\bORD-\d+\b",                                                                     Intent.SHIPMENT_STATUS, 0.80)
_p(r"\bwhere\s*(?:is|are)\s+my\b",                                                     Intent.SHIPMENT_STATUS, 0.85)

# --- Delivery prediction ---------------------------------------------------
_p(r"\b(when|how\s+long|predict|estimate|eta|delivery\s+time)\b.*\b(deliver|arriv|ship|order)\b", Intent.DELIVERY_PREDICTION, 0.90)
_p(r"\b(deliver|arriv)\b.*\b(when|time|how\s+long|predict|eta)\b",                                Intent.DELIVERY_PREDICTION, 0.88)
_p(r"\bestimated\s+(delivery|arrival)\b",                                                          Intent.DELIVERY_PREDICTION, 0.90)

# --- Complaint -------------------------------------------------------------
_p(r"\b(complain|damaged|broken|wrong\s+item|not\s+received|missing|lost)\b",  Intent.COMPLAINT, 0.88)
_p(r"\b(file|make|lodge|submit)\s+(a\s+)?(complaint|claim|report)\b",          Intent.COMPLAINT, 0.90)
_p(r"\b(unhappy|dissatisfied|terrible|awful|worst)\b",                         Intent.COMPLAINT, 0.75)

# --- Reroute request -------------------------------------------------------
_p(r"\b(reroute|redirect|change\s+.{0,20}(address|destination)|new\s+address)\b", Intent.REROUTE_REQUEST, 0.90)
_p(r"\b(send|deliver)\s+(it\s+)?to\s+(a\s+)?different\b",                            Intent.REROUTE_REQUEST, 0.85)

# --- Escalation ------------------------------------------------------------
_p(r"\b(speak|talk)\s+(to|with)\s+(a\s+)?(human|agent|person|representative|manager)\b", Intent.ESCALATION, 0.92)
_p(r"\bescalat",                                                                            Intent.ESCALATION, 0.90)
_p(r"\b(transfer|connect\s+me)\b",                                                         Intent.ESCALATION, 0.88)

# --- FAQ -------------------------------------------------------------------
_p(r"\b(what|how)\s+(does|do|is|are)\b.*\b(work|mean|policy|policies)\b",  Intent.FAQ, 0.75)
_p(r"\b(tell\s+me\s+about|explain|what\s+is)\b",                           Intent.FAQ, 0.70)
_p(r"\breturn\s+policy\b",                                                  Intent.FAQ, 0.85)
_p(r"\b(faq|help|information)\b",                                           Intent.FAQ, 0.70)

# --- Greeting / farewell ---------------------------------------------------
_p(r"^\s*(hi|hello|hey|good\s+(morning|afternoon|evening)|greetings)\b", Intent.GREETING, 0.95)
_p(r"^\s*(bye|goodbye|see\s+you|thanks?|thank\s+you|that\s*'?s?\s+all)\b", Intent.FAREWELL, 0.95)


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

_ORDER_ID_RE   = re.compile(r"\b(ORD-\d{3,})\b", re.IGNORECASE)
_CUSTOMER_ID_RE = re.compile(r"\b(CUST-\d{3,})\b", re.IGNORECASE)
_CITY_RE        = re.compile(
    r"\b(New York|Los Angeles|Chicago|Houston|Dallas|Miami|Atlanta|Denver|Seattle|Phoenix"
    r"|San Francisco|Boston|Portland|Detroit|Minneapolis)\b",
    re.IGNORECASE,
)


def _extract_entities(text: str) -> Dict[str, str]:
    """Pull known entity types from the raw query text."""
    entities: Dict[str, str] = {}

    m = _ORDER_ID_RE.search(text)
    if m:
        entities["order_id"] = m.group(1).upper()

    m = _CUSTOMER_ID_RE.search(text)
    if m:
        entities["customer_id"] = m.group(1).upper()

    cities = _CITY_RE.findall(text)
    if cities:
        entities["city"] = cities[0]
        if len(cities) >= 2:
            entities["origin"] = cities[0]
            entities["destination"] = cities[1]

    return entities


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_intent(query: str) -> ParsedIntent:
    """
    Parse a natural-language query and return the detected intent + entities.

    The function iterates through all registered patterns, picks the match
    with the **highest confidence**, and extracts entities from the raw text.
    """
    if not query or not query.strip():
        return ParsedIntent(intent=Intent.UNKNOWN, confidence=0.0, raw_query=query)

    text = query.strip()
    best_intent: Intent = Intent.UNKNOWN
    best_conf: float = 0.0

    for pattern, intent, base_conf in _INTENT_PATTERNS:
        if pattern.search(text):
            if base_conf > best_conf:
                best_intent = intent
                best_conf = base_conf

    entities = _extract_entities(text)

    # Boost confidence if we found a matching entity for the intent
    if best_intent == Intent.SHIPMENT_STATUS and "order_id" in entities:
        best_conf = min(best_conf + 0.05, 1.0)
    if best_intent == Intent.REROUTE_REQUEST and ("city" in entities or "destination" in entities):
        best_conf = min(best_conf + 0.05, 1.0)

    result = ParsedIntent(
        intent=best_intent,
        confidence=round(best_conf, 3),
        entities=entities,
        raw_query=text,
    )

    logger.debug("Intent: {} (conf={:.2f}) | entities={}", result.intent.value, result.confidence, result.entities)
    return result
