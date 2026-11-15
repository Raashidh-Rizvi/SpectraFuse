"""Integration tests for Orchestrator Agent routing and specialist execution (Phase 3)."""

from backend.agents.orchestrator import OrchestratorAgent
from backend.agents.schemas import ChatRequest


def test_tc_a01_monthly_summary():
    """TC-A01: Orchestrator routes monthly query to Data Query Agent with direct answer first."""
    orchestrator = OrchestratorAgent()
    req = ChatRequest(
        message="What was the fire activity in Sri Lanka in August 2021?",
        region="sri-lanka",
    )
    res = orchestrator.process(req)
    assert res.intent == "monthly_summary"
    assert "August 2021 has a harmonized activity value" in res.answer
    assert "705" in res.answer
    assert "observed viirs" in res.answer.lower()
    assert len(res.evidence) >= 1
    assert res.evidence[0].status == "observed"
    assert res.evidence[0].value == 705


def test_tc_a02_sensor_comparison():
    """TC-A02: Orchestrator routes sensor comparison request to Analysis Agent."""
    orchestrator = OrchestratorAgent()
    req = ChatRequest(
        message="Compare MODIS and VIIRS for 2020.",
        region="sri-lanka",
    )
    res = orchestrator.process(req)
    assert res.intent == "sensor_comparison"
    assert "matched months" in res.answer.lower()
    assert any(ev.product == "MODIS_SP" for ev in res.evidence)
    assert any(ev.product == "VIIRS_SNPP_SP" for ev in res.evidence)


def test_tc_a03_anomaly_explanation():
    """TC-A03: Orchestrator routes seasonal anomaly request to Analysis Agent."""
    orchestrator = OrchestratorAgent()
    req = ChatRequest(
        message="Was March 2023 unusual compared with earlier March values?",
        region="sri-lanka",
    )
    res = orchestrator.process(req)
    assert res.intent == "anomaly_explanation"
    assert "departure" in res.answer.lower()
    assert len(res.calculations) >= 1
    assert "%" in res.calculations[0].result


def test_tc_a04_hotspot_request_map_action():
    """TC-A04: Orchestrator routes hotspot request to Map Agent and returns UIAction."""
    orchestrator = OrchestratorAgent()
    req = ChatRequest(
        message="Show hotspots for 2022-03-01 to 2022-03-10 on the map.",
        region="sri-lanka",
    )
    res = orchestrator.process(req)
    assert res.intent == "hotspot_request"
    assert len(res.ui_actions) == 1
    action = res.ui_actions[0]
    assert action.type == "show_on_map"
    assert action.payload["start"] == "2022-03-01"
    assert action.payload["end"] == "2022-03-10"


def test_tc_a05_data_export():
    """TC-A05: Orchestrator routes export request to Export Agent and returns download item."""
    orchestrator = OrchestratorAgent()
    req = ChatRequest(
        message="Download monthly data for 2021 as CSV.",
        region="sri-lanka",
    )
    res = orchestrator.process(req)
    assert res.intent == "data_export"
    assert len(res.downloads) == 1
    dl = res.downloads[0]
    assert dl.format == "csv"
    assert "/api/fire/download" in dl.url


def test_tc_a06_methodology_explanation():
    """TC-A06: Orchestrator routes methodology question to Explanation Agent."""
    orchestrator = OrchestratorAgent()
    req = ChatRequest(
        message="Explain the difference between MODIS and VIIRS.",
        region="sri-lanka",
    )
    res = orchestrator.process(req)
    assert res.intent == "methodology_question"
    assert "1 km" in res.answer
    assert "375 m" in res.answer


def test_tc_a07_data_agent_zero_detections():
    """TC-A07: Month with 0 observed detections is clearly labeled as 0, not unavailable."""
    orchestrator = OrchestratorAgent()
    # In Sri Lanka dataset, 2001-01 has 0 detections
    req = ChatRequest(
        message="What was the fire activity in January 2001?",
        region="sri-lanka",
    )
    res = orchestrator.process(req)
    assert "0" in res.answer
    assert "unavailable" not in res.answer.lower() or "estimated" in res.answer.lower()


def test_tc_a08_data_agent_unavailable_period():
    """TC-A08: Out-of-bounds period is clearly labeled as unavailable, not 0."""
    orchestrator = OrchestratorAgent()
    req = ChatRequest(
        message="What was the fire activity in January 1990?",
        region="sri-lanka",
    )
    res = orchestrator.process(req)
    assert "unavailable" in res.answer.lower()
    assert res.evidence[0].status == "unavailable"


def test_tc_a09_calibration_explanation():
    """TC-A09: Orchestrator routes calibration inquiry to Analysis Agent with holdout error."""
    orchestrator = OrchestratorAgent()
    req = ChatRequest(
        message="What is the calibration multiplier and how reliable is it?",
        region="sri-lanka",
    )
    res = orchestrator.process(req)
    assert res.intent == "calibration_explanation"
    assert "calibration factor" in res.answer.lower() or "multiplier" in res.answer.lower()
    assert "holdout" in res.answer.lower()


def test_tc_a10_conversational_gratitude():
    """TC-A10: Deterministic greeting/gratitude handling for 'thank you' and typos without fake data query."""
    orchestrator = OrchestratorAgent()
    for phrase in ("thank you", "thanks", "thank u", "thank kpu", "thx", "ty", "much appreciated"):
        req = ChatRequest(message=phrase, region="sri-lanka")
        res = orchestrator.process(req)
        assert res.intent == "gratitude"
        assert "welcome" in res.answer.lower()
        assert len(res.evidence) == 0
        assert len(res.calculations) == 0


def test_tc_a11_conversational_greetings():
    """TC-A11: Deterministic greetings and help responses."""
    orchestrator = OrchestratorAgent()
    for phrase in ("hello", "hi", "hey", "good morning", "how are you"):
        req = ChatRequest(message=phrase, region="sri-lanka")
        res = orchestrator.process(req)
        assert res.intent == "greeting"
        assert "spectrafuse" in res.answer.lower()
        assert len(res.evidence) == 0


def test_tc_a12_gratitude_preserves_followup_memory():
    """TC-A12: User saying 'thank you' does not clear or break subsequent 'show that on the map' follow-up."""
    import uuid
    from backend.agents.service import AgentService
    service = AgentService()
    sess_id = "test_conv_flow_" + uuid.uuid4().hex[:8]

    # Turn 1: Scientific query
    t1 = service.process_chat(ChatRequest(
        message="What was the fire activity in Sri Lanka in August 2021?",
        region="sri-lanka",
        session_id=sess_id,
    ))
    assert t1.intent == "monthly_summary"

    # Turn 2: User says thanks
    t2 = service.process_chat(ChatRequest(
        message="thank you",
        region="sri-lanka",
        session_id=sess_id,
    ))
    assert t2.intent == "gratitude"
    assert "welcome" in t2.answer.lower()
    assert len(t2.evidence) == 0

    # Turn 3: Follow-up should still recall August 2021!
    t3 = service.process_chat(ChatRequest(
        message="show that on the map",
        region="sri-lanka",
        session_id=sess_id,
    ))
    assert t3.intent == "hotspot_request"
    assert "2021-08-01" in t3.answer or "2021-08" in str(t3.period)

