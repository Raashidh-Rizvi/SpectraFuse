"""Integration tests for SpectraFuse Chat Endpoints, Session Memory, and Telemetry (Phase 4).

Validates:
- TC-E01: Health check endpoint
- TC-E02: Capabilities endpoint
- TC-E03: Standard chat execution
- TC-E04: Follow-up memory continuity (month transition)
- TC-E05: Follow-up 'explain above' contextual reasoning without deflection
- TC-E06: Follow-up 'show that on the map' UI action generation from memory
- TC-E07: STM window management (4 pairs / 8 turns cap)
- TC-E08: Input length limit (> 4000 chars rejected)
- TC-E09: Unknown region validation
- TC-E10: Telemetry audit logging without secrets
- TC-E11: Multi-session isolation
- TC-E12: Session deletion / memory reset endpoint
"""

import logging
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.agents.memory import get_session_store


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_memory_store():
    """Ensure clean memory store before each test."""
    store = get_session_store()
    store._sessions.clear()
    yield
    store._sessions.clear()


def test_tce01_chat_health(client):
    """TC-E01: Health check returns status, provider, and active regions."""
    res = client.get("/api/fire/chat/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "provider" in data
    assert "sri-lanka" in data["active_regions"]
    assert data["stm_max_pairs"] == 4


def test_tce02_chat_capabilities(client):
    """TC-E02: Capabilities endpoint returns supported intents, tools, and sensors."""
    res = client.get("/api/fire/chat/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "monthly_summary" in data["supported_intents"]
    assert "followup_explanation" in data["supported_intents"]
    assert "list_regions" in data["deterministic_tools"]
    assert "harmonized" in data["sensors"]
    assert data["memory"]["stm_max_pairs"] == 4
    assert data["memory"]["reference_resolution"] is True


def test_tce03_post_chat_standard(client):
    """TC-E03: POST /api/fire/chat returns valid ChatResponse structure."""
    payload = {
        "message": "What was the fire activity in Sri Lanka in August 2021?",
        "region": "sri-lanka",
        "session_id": "test_sess_01",
    }
    res = client.post("/api/fire/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["request_id"].startswith("req_")
    assert data["session_id"] == "test_sess_01"
    assert data["intent"] == "monthly_summary"
    assert "705" in data["answer"]
    assert len(data["evidence"]) >= 1
    assert data["evidence"][0]["status"] == "observed"


def test_tce04_session_continuity_next_month(client):
    """TC-E04: Session memory retains year and region when asking about another month."""
    sid = "test_sess_continuity"

    # Turn 1: Ask about August 2021
    res1 = client.post("/api/fire/chat", json={
        "message": "What was the fire activity in Sri Lanka in August 2021?",
        "region": "sri-lanka",
        "session_id": sid,
    })
    assert res1.status_code == 200
    assert "705" in res1.json()["answer"]

    # Turn 2: Follow-up: "What about September?" (omitting year and region)
    res2 = client.post("/api/fire/chat", json={
        "message": "What about September?",
        "session_id": sid,
    })
    assert res2.status_code == 200
    data2 = res2.json()
    # Should resolve to September 2021 in Sri Lanka
    assert data2["intent"] == "monthly_summary"
    assert "september 2021" in data2["answer"].lower() or "2021-09" in str(data2.get("period"))


def test_tce05_followup_explain_above_without_deflection(client):
    """TC-E05: 'Explain above' reasons over prior turn without saying 'please share details'."""
    sid = "test_sess_explain"

    # Turn 1: Initial question
    client.post("/api/fire/chat", json={
        "message": "What was the fire activity in Sri Lanka in August 2021?",
        "region": "sri-lanka",
        "session_id": sid,
    })

    # Turn 2: Follow-up question: "Explain above"
    res2 = client.post("/api/fire/chat", json={
        "message": "Explain above",
        "session_id": sid,
    })
    assert res2.status_code == 200
    data2 = res2.json()
    answer = data2["answer"]

    # Must NOT ask the user to share details
    assert "please share details" not in answer.lower()
    assert "i can help you if you provide" not in answer.lower()

    # Must reference the August 2021 / 705 detections / seasonal dry zone context
    assert "august 2021" in answer.lower() or "705" in answer
    assert data2["intent"] == "followup_explanation"
    assert len(data2["evidence"]) >= 1


def test_tce06_followup_show_on_map(client):
    """TC-E06: 'Show that on the map' generates show_on_map action from memory period."""
    sid = "test_sess_map"

    # Turn 1: Monthly query
    client.post("/api/fire/chat", json={
        "message": "What was the fire activity in Sri Lanka in August 2021?",
        "region": "sri-lanka",
        "session_id": sid,
    })

    # Turn 2: Follow-up: "Show that on the map"
    res2 = client.post("/api/fire/chat", json={
        "message": "Show that on the map",
        "session_id": sid,
    })
    assert res2.status_code == 200
    data2 = res2.json()

    assert len(data2["ui_actions"]) >= 1
    action = data2["ui_actions"][0]
    assert action["type"] == "show_on_map"
    assert action["payload"]["region"] == "sri-lanka"
    assert "2021-08" in action["payload"]["start"]


def test_tce07_stm_memory_window_cap(client):
    """TC-E07: Memory maintains the configured STM window (max 4 pairs / 8 turns)."""
    sid = "test_sess_window"
    store = get_session_store()

    # Perform 5 turns (10 messages total)
    for i in range(1, 6):
        client.post("/api/fire/chat", json={
            "message": f"What was the fire activity in August 202{i % 4}?",
            "region": "sri-lanka",
            "session_id": sid,
        })

    session = store.get(sid)
    assert session is not None
    # Maximum turns in STM is max_pairs * 2 = 8 turns
    assert len(session.turns) <= 8


def test_tce08_message_length_limit(client):
    """TC-E08: Messages > 4000 characters are rejected with HTTP 422."""
    long_msg = "A" * 4005
    res = client.post("/api/fire/chat", json={
        "message": long_msg,
        "region": "sri-lanka",
    })
    assert res.status_code == 422
    assert "4000" in str(res.json()["detail"])


def test_tce09_unknown_region_validation(client):
    """TC-E09: Unknown region returns HTTP 422 with supported suggestions."""
    res = client.post("/api/fire/chat", json={
        "message": "What was fire activity in Atlantis?",
        "region": "atlantis-invalid-zone",
    })
    assert res.status_code == 422
    assert "Unknown region 'atlantis-invalid-zone'" in res.json()["detail"]
    assert "sri-lanka" in res.json()["detail"]


def test_tce10_telemetry_logging(client, caplog):
    """TC-E10: Telemetry emits structured audit logs without private credentials."""
    caplog.set_level(logging.INFO, logger="spectrafuse.agents")

    client.post("/api/fire/chat", json={
        "message": "What was the fire activity in Sri Lanka in August 2021?",
        "region": "sri-lanka",
        "session_id": "sess_telemetry_audit",
    })

    log_texts = [record.message for record in caplog.records if "TELEMETRY:" in record.message]
    assert len(log_texts) >= 1
    log_line = log_texts[0]

    assert "request_id=" in log_line
    assert "session_id=sess_telemetry_audit" in log_line
    assert "intent=monthly_summary" in log_line
    assert "duration_ms=" in log_line
    assert "gsk_" not in log_line
    assert "FIRMS_MAP_KEY" not in log_line


def test_tce11_session_isolation(client):
    """TC-E11: Different session IDs have isolated memory contexts."""
    store = get_session_store()

    # Session A: Sri Lanka 2021
    client.post("/api/fire/chat", json={
        "message": "What was the fire activity in Sri Lanka in August 2021?",
        "region": "sri-lanka",
        "session_id": "session_alpha",
    })

    # Session B: Central Thailand
    client.post("/api/fire/chat", json={
        "message": "What was the fire activity in 101,14,102,15 in March 2022?",
        "region": "101,14,102,15",
        "session_id": "session_beta",
    })

    sess_a = store.get("session_alpha")
    sess_b = store.get("session_beta")
    assert sess_a is not None
    assert sess_b is not None

    assert sess_a.active_region == "sri-lanka"
    assert sess_a.active_year == 2021
    assert sess_a.active_month == 8

    assert sess_b.active_region == "101,14,102,15"
    assert sess_b.active_year == 2022
    assert sess_b.active_month == 3


def test_tce12_clear_session_endpoint(client):
    """TC-E12: DELETE /api/fire/chat/session/{session_id} resets memory."""
    sid = "sess_to_delete"
    store = get_session_store()

    client.post("/api/fire/chat", json={
        "message": "What was the fire activity in Sri Lanka in August 2021?",
        "region": "sri-lanka",
        "session_id": sid,
    })
    assert store.get(sid) is not None

    del_res = client.delete(f"/api/fire/chat/session/{sid}")
    assert del_res.status_code == 200
    assert del_res.json() == {"session_id": sid, "deleted": True}
    assert store.get(sid) is None
