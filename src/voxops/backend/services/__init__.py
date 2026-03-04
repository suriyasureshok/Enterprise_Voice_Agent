"""
voxops.backend.services package — AI Reasoning & Orchestration.

Public API
----------
Intent, ParsedIntent, parse_intent — intent detection from user queries.
OrchestratorResult, process_query  — end-to-end query pipeline.
generate_response                  — natural-language response formatting.
HandoffResult, create_handoff      — agent handoff / ticket creation.
"""

from src.voxops.backend.services.intent_parser import Intent, ParsedIntent, parse_intent
from src.voxops.backend.services.orchestrator import OrchestratorResult, process_query
from src.voxops.backend.services.response_generator import generate_response
from src.voxops.backend.services.agent_handoff import HandoffResult, create_handoff

__all__ = [
    "Intent",
    "ParsedIntent",
    "parse_intent",
    "OrchestratorResult",
    "process_query",
    "generate_response",
    "HandoffResult",
    "create_handoff",
]
