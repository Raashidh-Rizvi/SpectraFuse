from unittest.mock import Mock

import pandas as pd

from backend import chat, main


def test_chat_grounds_answer_in_matched_sensor_months(monkeypatch):
    frame = pd.DataFrame({
        "MODIS_SP": [0, 10, 100],
        "VIIRS_SNPP_SP": [None, 20, None],
        "VIIRS_NOAA20_SP": [None, 30, None],
        "harmonized": [None, 20, None],
        "origin": ["Missing", "Observed by VIIRS", "Missing"],
    }, index=pd.Index(["2024-01", "2024-02", "2024-03"], name="month"))
    monkeypatch.setattr(main, "dashboard_frame", lambda region: frame)
    monkeypatch.setattr(chat, "load_dotenv", lambda path: None)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setenv("OPENAI_MODEL", "fixture-model")
    provider = Mock(return_value=Mock(status_code=200))
    provider.return_value.json.return_value = {"choices": [{"message": {"content": "February was the only matched month."}}]}
    monkeypatch.setattr(chat.requests, "post", provider)

    import json
    result = main.chat(chat.ChatRequest(question="Compare MODIS and VIIRS in 2024."))
    payload = provider.call_args.kwargs["json"]
    data = json.loads(payload["messages"][-1]["content"])["evidence"]
    summary = data["annual"]["2024"]
    assert summary["matched_sensor_comparisons"]["MODIS_SP vs VIIRS_SNPP_SP"] == {
        "months": 1, "totals_in_sensor_order": [10, 20],
    }
    assert data["monthly_rows"][0][1:3] == [0, None]
    assert payload["store"] is False
    assert result["first_month"] == "2024-01"
    assert result["answer"] == "February was the only matched month."
