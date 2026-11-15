import json
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import chat, main
from backend.agents import service
from backend.fire import workspace


@pytest.fixture
def archive(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRESCOPE_DATA_DIR", str(tmp_path))
    root = workspace(main.PILOT)
    root.mkdir()
    (root / "area.txt").write_text(main.PILOT)
    return root


@pytest.fixture
def frame():
    return pd.DataFrame({
        "MODIS_SP": [90, 0, 10, None, 20],
        "VIIRS_SNPP_SP": [None, None, 30, None, 40],
        "harmonized": [None, None, 30, None, 40],
        "origin": ["Unavailable", "Unavailable", "Observed by VIIRS", "Unavailable", "Observed by VIIRS"],
    }, index=pd.Index(["2023-12", "2024-01", "2024-02", "2024-03", "2024-04"], name="month"))


def provider_mock(monkeypatch, *contents):
    monkeypatch.setattr(chat, "load_dotenv", Mock())
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setenv("OPENAI_MODEL", "fixture-model")
    responses = [Mock(status_code=200, **{"json.return_value": {"choices": [{"message": {"content": content}}]}})
                 for content in contents]
    provider = Mock(side_effect=responses)
    monkeypatch.setattr(chat.requests, "post", provider)
    return provider

def test_oldest_uses_product_daily_coverage_without_monthly_table(monkeypatch, archive):
    modis = archive / "processed" / "MODIS_SP"
    modis.mkdir(parents=True)
    for filename in ("2000-11-17.parquet", "2000-11-19.parquet", "1999-02-30.parquet"):
        (modis / filename).touch()
    monkeypatch.setattr(main, "calendar_table", Mock(side_effect=AssertionError("monthly table was read")))
    provider = provider_mock(monkeypatch)

    result = main.chat(chat.ChatRequest(question="What is the oldest data available in the MODIS dataset?"))

    assert "2000-11-17 UTC" in result["answer"]
    assert result["citations"] == [{"product": "MODIS_SP", "basis": "daily_partitions",
                                   "first": "2000-11-17", "last": "2000-11-19", "available": 2,
                                   "expected": 3, "start_month": "2000-11", "end_month": "2000-11"}]
    provider.assert_not_called()


def test_mean_keeps_zero_and_excludes_missing_in_requested_year(monkeypatch, archive, frame):
    monkeypatch.setattr(main, "calendar_table", lambda region: frame)
    monkeypatch.setattr(main, "noaa_monthly_counts", Mock(side_effect=AssertionError("NOAA-20 was read")))
    provider = provider_mock(monkeypatch)
    result = main.chat(chat.ChatRequest(question="What's the mean monthly fire detections for MODIS in 2024?"))

    assert "10.00 detections per UTC month" in result["answer"]
    assert "3 of 12 months" in result["answer"]
    assert result["first_month"] == "2024-01"
    assert result["last_month"] == "2024-04"
    provider.assert_not_called()


def test_retrieves_matched_months_for_follow_up(monkeypatch, archive, frame):
    get_frame = Mock(return_value=frame)
    monkeypatch.setattr(main, "calendar_table", get_frame)
    plan = {"lookups": [{"kind": "comparison", "products": ["MODIS_SP", "VIIRS_SNPP_SP"],
                         "start_month": "2024-01", "end_month": "2024-03"},
                        {"kind": "monthly", "products": ["MODIS_SP"],
                         "start_month": "2024-01", "end_month": "2024-03"}]}
    provider = provider_mock(monkeypatch, json.dumps(plan), "February was the only matched month.")
    result = main.chat(chat.ChatRequest(question="And how does it compare with S-NPP over that period?",
                                       history=[{"role": "user", "content": "MODIS in January to March 2024"}]))

    planning, synthesis = [call.kwargs["json"] for call in provider.call_args_list]
    assert planning["response_format"] == {"type": "json_object"}
    assert "January to March 2024" in planning["messages"][-1]["content"]
    assert planning["store"] is synthesis["store"] is False
    evidence = json.loads(synthesis["messages"][-1]["content"])["evidence"]
    modis, viirs, monthly = evidence
    assert [modis["total"], viirs["total"]] == [10, 30]
    assert modis["citation"]["available"] == viirs["citation"]["available"] == 1
    assert monthly["mean"] == 5
    assert monthly["monthly_values"] == {"2024-01": 0, "2024-02": 10}
    assert result["answer"] == "February was the only matched month."
    assert result["citations"] == [item["citation"] for item in evidence]
    get_frame.assert_called_once_with("sri-lanka")


def test_frp_uses_per_detection_mean_and_reports_partial_cover(monkeypatch, archive):
    modis = archive / "processed" / "MODIS_SP"
    modis.mkdir(parents=True)
    for day, values in (("2024-02-01", [0, 6, None]), ("2024-02-10", [24]), ("2024-03-01", [100])):
        pd.DataFrame({"frp": pd.Series(values, dtype="Float64")}).to_parquet(modis / f"{day}.parquet")
    plan = {"lookups": [{"kind": "frp", "products": ["MODIS_SP"],
                         "start_month": "2024-02", "end_month": "2024-02"}]}
    provider = provider_mock(monkeypatch, json.dumps(plan), "The mean was 10 MW per detection.")
    result = main.chat(chat.ChatRequest(question="Using the available days, how much MODIS FRP was recorded per detection on average in Feb 2024?"))

    evidence = json.loads(provider.call_args.kwargs["json"]["messages"][-1]["content"])["evidence"][0]
    assert (evidence["mean"], evidence["minimum"], evidence["maximum"], evidence["detections_with_frp"]) == (10, 0, 24, 3)
    assert evidence["units"] == "MW per detection"
    assert (result["citations"][0]["available"], result["citations"][0]["expected"]) == (2, 29)


def test_ambiguous_question_requests_clarification(monkeypatch, archive):
    provider = provider_mock(monkeypatch, '{"lookups": [], "reply": "Which product and metric should I average?"}')
    result = main.chat(chat.ChatRequest(question="What's the mean value?"))

    assert result["answer"] == "Which product and metric should I average?"
    assert result["citations"] == []
    provider.assert_called_once()


def test_noaa_only_month_is_included_in_monthly_evidence(monkeypatch, archive, frame):
    monkeypatch.setattr(main, "calendar_table", lambda region: frame)
    counts = pd.Series({"2024-05": 18}, name="VIIRS_NOAA20_SP").rename_axis("month")
    monkeypatch.setattr(main, "noaa_monthly_counts", lambda area: counts)

    result = main.chat(chat.ChatRequest(question="What is the average monthly detections for NOAA-20 in 2024?"))

    assert "18.00 detections per UTC month" in result["answer"]
    assert result["last_month"] == "2024-05"


def test_invalid_lookup_is_rejected_before_retrieval(monkeypatch, archive):
    provider = provider_mock(monkeypatch, '{"lookups": [{"kind": "coverage", "products": ["../raw"]}]}')
    fetch = Mock()
    monkeypatch.setattr(chat, "retrieve", fetch)

    with pytest.raises(HTTPException, match="supported lookup") as error:
        main.chat(chat.ChatRequest(question="Which data is available?"))

    assert error.value.status_code == 502
    fetch.assert_not_called()
    provider.assert_called_once()


def test_dashboard_agent_uses_archive_coverage_and_mean(monkeypatch, archive, frame):
    modis = archive / "processed" / "MODIS_SP"
    modis.mkdir(parents=True)
    (modis / "2000-11-17.parquet").touch()
    pd.DataFrame({"frp": [6.0, 24.0]}).to_parquet(modis / "2024-02-01.parquet")
    monkeypatch.setattr(main, "calendar_table", lambda region: frame)
    explanation = Mock(side_effect=AssertionError("archive answers must keep their verified evidence"))
    monkeypatch.setattr(service, "explain", explanation)
    cases = [
        ("what is the oldest data available on the modis dataset", "2000-11-17 UTC", "2000-11-17"),
        ("And the latest?", "2024-02-01 UTC", "2024-02-01"),
        ("How far back does MODIS go?", "2000-11-17 UTC", "2000-11-17"),
        ("What dates does the MODIS archive cover?", "2000-11-17 through 2024-02-01 UTC",
         {"first": "2000-11-17", "last": "2024-02-01"}),
        ("How many MODIS detections per month on average in 2024?", "10.00 detections per UTC month", 10),
        ("What was the mean MODIS FRP in February 2024?", "15.00 MW per detection", 15),
    ]

    with TestClient(main.app) as client:
        for question, text, value in cases:
            response = client.post("/api/fire/chat", json={"message": question, "session_id": "archive-lookup-test"})
            assert response.status_code == 200
            assert text in response.json()["answer"]
            assert response.json()["evidence"][0]["value"] == value
        legacy = client.post("/api/fire/chat", json={"question": cases[0][0]})
        assert legacy.status_code == 200
        assert legacy.json()["citations"][0]["first"] == "2000-11-17"
    explanation.assert_not_called()


@pytest.mark.parametrize("question", ["What's the mean value?", "What is available here?", "Where is Mount Everest?"])
def test_dashboard_unresolved_question_does_not_guess_a_month(monkeypatch, archive, question):
    monkeypatch.setattr(chat, "load_dotenv", Mock())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(main, "calendar_table", Mock(side_effect=AssertionError("no monthly lookup was requested")))

    with TestClient(main.app) as client:
        response = client.post("/api/fire/chat", json={"message": question})

    assert response.status_code == 200
    assert response.json()["intent"] == "clarification"
    assert response.json()["evidence"] == []
    assert response.json()["limitations"] == []
    assert "August 2021" not in response.json()["answer"]


@pytest.mark.parametrize(("question", "statistic", "end_month", "coverage"), [
    ("Find the median of MODIS monthly detections from January to April 2024.", "median", "2024-04", "3 of 4"),
    ("What were the average monthly MODIS detections in the first half of 2024?", "mean", "2024-06", "3 of 6"),
])
def test_dashboard_model_fallback_retrieves_requested_statistic(monkeypatch, archive, frame, question, statistic, end_month, coverage):
    monkeypatch.setattr(main, "calendar_table", lambda region: frame)
    plan = {"lookups": [{"kind": "monthly", "products": ["MODIS_SP"],
                         "start_month": "2024-01", "end_month": end_month}]}
    provider = provider_mock(monkeypatch, json.dumps(plan), f"The {statistic} was 10 MODIS detections per month.")

    with TestClient(main.app) as client:
        response = client.post("/api/fire/chat", json={"message": question})

    assert response.status_code == 200
    assert response.json()["intent"] == "archive_analysis"
    assert response.json()["evidence"][0]["value"][statistic] == 10
    assert response.json()["evidence"][0]["coverage"] == coverage
    assert provider.call_count == 2
