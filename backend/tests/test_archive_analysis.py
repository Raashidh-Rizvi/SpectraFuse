import pandas as pd

from backend.agents.orchestrator import OrchestratorAgent
from backend.agents.schemas import ChatRequest


def test_compares_only_requested_months_and_preserves_zero(monkeypatch):
    frame = pd.DataFrame(
        {"harmonized": [0, 100, 12], "origin": ["Observed by VIIRS"] * 3},
        index=pd.Index(["2021-01", "2022-01", "2023-02"], name="month"),
    )
    monkeypatch.setattr("backend.main.dashboard_frame", lambda region: frame)
    result = OrchestratorAgent().process(ChatRequest(message="Compare January 2021 and February 2023"))
    assert result.intent == "trend_analysis"
    assert [item.value for item in result.evidence] == [0, 12]
    assert "+12.0 detections" in result.answer
    assert "percent change undefined from zero" in result.answer
