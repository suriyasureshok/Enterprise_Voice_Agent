"""
VOXOPS AI Gateway — Phase 7 Tests: AI Reasoning & Orchestration

Covers:
  1. Intent Parser       — pattern matching, entity extraction, confidence
  2. Response Generator  — all intent formatters
  3. Agent Handoff       — ticket creation, transcript storage, priority mapping
  4. Orchestrator        — full pipeline integration with DB
  5. Voice Endpoint      — API integration via orchestrator
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture(autouse=True)
def _reset_handoff():
    """Clear handoff transcript store between tests."""
    from src.voxops.backend.services.agent_handoff import clear_transcripts
    clear_transcripts()
    yield
    clear_transcripts()


# ======================================================================
# 1. Intent Parser
# ======================================================================

class TestIntentParser:

    def test_shipment_status_basic(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("Where is my order?")
        assert r.intent == Intent.SHIPMENT_STATUS

    def test_shipment_status_with_order_id(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("Track my shipment ORD-001")
        assert r.intent == Intent.SHIPMENT_STATUS
        assert r.entities.get("order_id") == "ORD-001"
        assert r.confidence > 0.85

    def test_shipment_status_order_id_only(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("ORD-005")
        assert r.intent == Intent.SHIPMENT_STATUS
        assert r.entities.get("order_id") == "ORD-005"

    def test_delivery_prediction(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("When will my order ORD-003 be delivered?")
        assert r.intent == Intent.DELIVERY_PREDICTION
        assert r.entities.get("order_id") == "ORD-003"

    def test_delivery_prediction_eta(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("What is the estimated delivery time for my shipment?")
        assert r.intent == Intent.DELIVERY_PREDICTION

    def test_complaint_damaged(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("My package arrived damaged")
        assert r.intent == Intent.COMPLAINT

    def test_complaint_missing(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("I haven't received my order, it's missing")
        assert r.intent == Intent.COMPLAINT

    def test_complaint_file_claim(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("I want to file a complaint about my delivery")
        assert r.intent == Intent.COMPLAINT

    def test_reroute_request(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("Can I change the delivery address for my order?")
        assert r.intent == Intent.REROUTE_REQUEST

    def test_reroute_redirect(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("Please reroute my package to a new address")
        assert r.intent == Intent.REROUTE_REQUEST

    def test_escalation(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("I want to speak to a human agent")
        assert r.intent == Intent.ESCALATION

    def test_escalation_transfer(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("Please escalate this issue")
        assert r.intent == Intent.ESCALATION

    def test_faq(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("What is the return policy?")
        assert r.intent == Intent.FAQ

    def test_faq_explain(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("Tell me about your delivery policies")
        assert r.intent == Intent.FAQ

    def test_greeting(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("Hello!")
        assert r.intent == Intent.GREETING

    def test_farewell(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("Goodbye, thanks!")
        assert r.intent == Intent.FAREWELL

    def test_unknown(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("asdfghjkl random noise")
        assert r.intent == Intent.UNKNOWN
        assert r.confidence == 0.0

    def test_empty_query(self):
        from src.voxops.backend.services.intent_parser import parse_intent, Intent
        r = parse_intent("")
        assert r.intent == Intent.UNKNOWN

    def test_entity_extraction_customer_id(self):
        from src.voxops.backend.services.intent_parser import parse_intent
        r = parse_intent("My customer ID is CUST-100, check order ORD-005")
        assert r.entities.get("customer_id") == "CUST-100"
        assert r.entities.get("order_id") == "ORD-005"

    def test_entity_extraction_cities(self):
        from src.voxops.backend.services.intent_parser import parse_intent
        r = parse_intent("Ship from Chicago to Miami please")
        assert "city" in r.entities or "origin" in r.entities

    def test_confidence_is_float(self):
        from src.voxops.backend.services.intent_parser import parse_intent
        r = parse_intent("Where is my order ORD-001?")
        assert isinstance(r.confidence, float)
        assert 0.0 <= r.confidence <= 1.0

    def test_parsed_intent_has_raw_query(self):
        from src.voxops.backend.services.intent_parser import parse_intent
        r = parse_intent("Track order ORD-002")
        assert r.raw_query == "Track order ORD-002"


# ======================================================================
# 2. Response Generator
# ======================================================================

class TestResponseGenerator:

    def test_shipment_status_found(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("shipment_status", {
            "order": {
                "order_id": "ORD-001",
                "status": "in_transit",
                "origin": "Chicago",
                "destination": "Houston",
            }
        })
        assert "ORD-001" in resp
        assert "in transit" in resp.lower()

    def test_shipment_status_not_found(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("shipment_status", {"order": None, "order_id": "ORD-999"})
        assert "ORD-999" in resp
        assert "couldn't find" in resp.lower() or "sorry" in resp.lower()

    def test_delivery_prediction(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("delivery_prediction", {
            "prediction": {
                "order_id": "ORD-001",
                "total_hours": 5.5,
                "delay_probability": 0.15,
                "summary": "",
            }
        })
        assert "ORD-001" in resp
        assert "hour" in resp.lower()

    def test_delivery_prediction_with_summary(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("delivery_prediction", {
            "prediction": {
                "order_id": "ORD-001",
                "total_hours": 3.0,
                "delay_probability": 0.1,
                "summary": "Delivery expected in 3.0 hours.",
            }
        })
        assert "3.0 hours" in resp

    def test_complaint_with_ticket(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("complaint", {
            "ticket": {"ticket_id": "TKT-ABC12345"}
        })
        assert "TKT-ABC12345" in resp
        assert "agent" in resp.lower()

    def test_complaint_no_ticket(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("complaint", {})
        assert "order id" in resp.lower() or "concern" in resp.lower()

    def test_reroute_in_transit(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("reroute_request", {
            "order": {"order_id": "ORD-001", "status": "in_transit"}
        })
        assert "$25" in resp or "fee" in resp.lower()

    def test_reroute_delivered(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("reroute_request", {
            "order": {"order_id": "ORD-001", "status": "delivered"}
        })
        assert "cannot" in resp.lower() or "already" in resp.lower()

    def test_faq_with_context(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("faq", {"rag_context": "Standard delivery is 3-5 days."})
        assert "3-5 days" in resp

    def test_escalation(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("escalation", {
            "ticket": {"ticket_id": "TKT-XYZ"}
        })
        assert "TKT-XYZ" in resp

    def test_greeting(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("greeting", {})
        assert "hello" in resp.lower() or "help" in resp.lower()

    def test_farewell(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("farewell", {})
        assert "thank" in resp.lower() or "day" in resp.lower()

    def test_unknown(self):
        from src.voxops.backend.services.response_generator import generate_response
        resp = generate_response("unknown", {})
        assert "not sure" in resp.lower() or "try again" in resp.lower()


# ======================================================================
# 3. Agent Handoff
# ======================================================================

class TestAgentHandoff:

    def test_create_handoff_basic(self):
        from src.voxops.backend.services.agent_handoff import create_handoff
        result = create_handoff(
            intent="complaint",
            query="My package is damaged",
            customer_id="CUST-001",
        )
        assert result.ticket_id.startswith("TKT-")
        assert result.customer_id == "CUST-001"
        assert result.priority == "high"
        assert result.status == "open"

    def test_handoff_priority_mapping(self):
        from src.voxops.backend.services.agent_handoff import create_handoff
        r1 = create_handoff(intent="complaint", query="Complaint")
        assert r1.priority == "high"
        r2 = create_handoff(intent="reroute_request", query="Reroute")
        assert r2.priority == "normal"
        r3 = create_handoff(intent="escalation", query="Escalate")
        assert r3.priority == "high"

    def test_handoff_summary_includes_query(self):
        from src.voxops.backend.services.agent_handoff import create_handoff
        result = create_handoff(
            intent="complaint",
            query="My package arrived broken",
            entities={"order_id": "ORD-005"},
        )
        assert "ORD-005" in result.issue_summary
        assert "broken" in result.issue_summary

    def test_handoff_stores_transcript(self):
        from src.voxops.backend.services.agent_handoff import create_handoff, get_transcript
        messages = [
            {"role": "user", "text": "My order is missing"},
            {"role": "system", "text": "I'll create a ticket for you."},
        ]
        result = create_handoff(
            intent="complaint",
            query="My order is missing",
            transcript_messages=messages,
        )
        assert result.transcript_stored is True
        stored = get_transcript(result.ticket_id)
        assert len(stored) == 2

    def test_handoff_no_transcript(self):
        from src.voxops.backend.services.agent_handoff import create_handoff, get_transcript
        result = create_handoff(intent="escalation", query="Connect me")
        assert result.transcript_stored is False
        assert get_transcript(result.ticket_id) == []

    def test_handoff_visible_in_routes_agent(self):
        from src.voxops.backend.services.agent_handoff import create_handoff
        from src.voxops.backend.api.routes_agent import _tickets
        result = create_handoff(intent="complaint", query="Bad service")
        assert result.ticket_id in _tickets

    def test_handoff_entity_fallback(self):
        from src.voxops.backend.services.agent_handoff import create_handoff
        result = create_handoff(
            intent="complaint",
            query="Problem with my order",
            entities={"customer_id": "CUST-050", "order_id": "ORD-010"},
        )
        assert result.customer_id == "CUST-050"


# ======================================================================
# 4. Orchestrator (with real DB)
# ======================================================================

class TestOrchestrator:

    def _get_db_session(self):
        from src.voxops.database.db import SessionLocal
        return SessionLocal()

    def test_greeting_pipeline(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("Hello!", db)
            assert result.intent == "greeting"
            assert result.needs_escalation is False
            assert "hello" in result.response_text.lower() or "help" in result.response_text.lower()
        finally:
            db.close()

    def test_farewell_pipeline(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("Goodbye, thanks!", db)
            assert result.intent == "farewell"
            assert result.needs_escalation is False
        finally:
            db.close()

    def test_shipment_status_pipeline(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("Where is my order ORD-001?", db)
            assert result.intent == "shipment_status"
            assert result.entities.get("order_id") == "ORD-001"
            assert "ORD-001" in result.response_text
            assert result.data.get("order") is not None
        finally:
            db.close()

    def test_shipment_status_not_found(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("Track order ORD-999", db)
            assert result.intent == "shipment_status"
            assert result.data.get("order") is None
            assert "sorry" in result.response_text.lower() or "couldn't find" in result.response_text.lower()
        finally:
            db.close()

    def test_delivery_prediction_pipeline(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("When will order ORD-001 be delivered?", db)
            assert result.intent == "delivery_prediction"
            assert result.data.get("prediction") is not None
            txt = result.response_text.lower()
            assert any(kw in txt for kw in ("hour", "minute", "delivery", "h (", "min"))
        finally:
            db.close()

    def test_complaint_pipeline_creates_ticket(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("My package ORD-002 arrived damaged!", db)
            assert result.intent == "complaint"
            assert result.needs_escalation is True
            assert result.handoff is not None
            assert result.handoff.ticket_id.startswith("TKT-")
            assert "TKT-" in result.response_text
        finally:
            db.close()

    def test_reroute_pipeline(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("I need to change the address for ORD-001", db)
            assert result.intent == "reroute_request"
            assert result.needs_escalation is True
            assert result.handoff is not None
        finally:
            db.close()

    def test_escalation_pipeline(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("I want to talk to a human agent", db)
            assert result.intent == "escalation"
            assert result.needs_escalation is True
            assert result.handoff is not None
            assert "TKT-" in result.response_text
        finally:
            db.close()

    def test_unknown_pipeline(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("xyzzy random gibberish 12345", db)
            assert result.intent == "unknown"
            assert result.needs_escalation is False
        finally:
            db.close()

    def test_customer_id_injected(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("Hello", db, customer_id="CUST-050")
            assert result.entities.get("customer_id") == "CUST-050"
        finally:
            db.close()

    def test_result_dataclass_fields(self):
        from src.voxops.backend.services.orchestrator import process_query
        db = self._get_db_session()
        try:
            result = process_query("Where is ORD-001?", db)
            assert hasattr(result, "transcript")
            assert hasattr(result, "intent")
            assert hasattr(result, "confidence")
            assert hasattr(result, "entities")
            assert hasattr(result, "response_text")
            assert hasattr(result, "data")
            assert hasattr(result, "handoff")
            assert hasattr(result, "needs_escalation")
        finally:
            db.close()


# ======================================================================
# 5. Voice Endpoint Integration
# ======================================================================

class TestVoiceEndpointIntegration:

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from src.voxops.backend.main import app
        return TestClient(app)

    def test_voice_text_shipment_status(self, client):
        resp = client.post("/voice/voice-query", data={"text": "Where is ORD-001?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "shipment_status"
        assert body["transcript"] == "Where is ORD-001?"
        assert "ORD-001" in body["response_text"]
        assert body["needs_escalation"] is False

    def test_voice_text_complaint_escalation(self, client):
        resp = client.post("/voice/voice-query", data={"text": "My package ORD-003 is damaged!"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "complaint"
        assert body["needs_escalation"] is True
        assert body["ticket_id"] is not None
        assert body["ticket_id"].startswith("TKT-")

    def test_voice_text_greeting(self, client):
        resp = client.post("/voice/voice-query", data={"text": "Hello!"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "greeting"

    def test_voice_text_delivery_prediction(self, client):
        resp = client.post("/voice/voice-query", data={"text": "When will my order ORD-001 be delivered?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "delivery_prediction"
        txt = body["response_text"].lower()
        assert any(kw in txt for kw in ("hour", "minute", "delivery", "h (", "min"))

    def test_voice_no_input_400(self, client):
        resp = client.post("/voice/voice-query")
        assert resp.status_code in (400, 422)

    def test_voice_response_has_confidence(self, client):
        resp = client.post("/voice/voice-query", data={"text": "Track ORD-001"})
        assert resp.status_code == 200
        body = resp.json()
        assert "confidence" in body
        assert isinstance(body["confidence"], float)

    def test_voice_response_has_entities(self, client):
        resp = client.post("/voice/voice-query", data={"text": "Track ORD-001"})
        assert resp.status_code == 200
        body = resp.json()
        assert "entities" in body
        assert body["entities"].get("order_id") == "ORD-001"
