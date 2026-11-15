"""Automated Evaluation Dataset Runner for SpectraFuse Agentic AI (Phase 7).

Executes the standardized benchmark matrix across all 22 evaluation cases (EV-01 to EV-22),
validating routing accuracy, tool selection, evidence provenance, numerical grounding,
and security guardrail interception.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from backend.agents.orchestrator import OrchestratorAgent
from backend.agents.schemas import ChatRequest

DATASET_PATH = Path(__file__).parent / "evaluation_dataset.json"


def load_evaluation_dataset() -> list[dict[str, Any]]:
    """Load test cases from the JSON evaluation suite."""
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


EVAL_CASES = load_evaluation_dataset()


@pytest.fixture(scope="module")
def orchestrator() -> OrchestratorAgent:
    """Instantiate shared OrchestratorAgent for evaluation runs."""
    return OrchestratorAgent()


@pytest.mark.parametrize(
    "item",
    EVAL_CASES,
    ids=[f"{c['id']}_{c['category']}" for c in EVAL_CASES],
)
def test_evaluation_case(orchestrator: OrchestratorAgent, item: dict[str, Any]):
    """Execute a single evaluation benchmark item and assert all constraints."""
    req = ChatRequest(
        message=item["question"],
        region=item.get("region", "sri-lanka"),
    )
    res = orchestrator.process(req)

    # 1. Intent routing assertion
    assert (
        res.intent == item["expected_intent"]
    ), f"[{item['id']}] Expected intent '{item['expected_intent']}', got '{res.intent}'"

    assertions = item.get("assertions", {})

    # 2. Required text contains assertions
    for text in assertions.get("contains_text", []):
        assert (
            text.lower() in res.answer.lower()
        ), f"[{item['id']}] Expected text '{text}' missing in response answer:\n{res.answer}"

    # 3. Disallowed text assertions (security / leaks / anti-hallucination)
    for text in assertions.get("disallowed_text", []):
        assert (
            text.lower() not in res.answer.lower()
        ), f"[{item['id']}] Disallowed text '{text}' detected in response answer:\n{res.answer}"

    # 4. Evidence count and status assertions
    if "min_evidence_count" in assertions:
        assert (
            len(res.evidence) >= assertions["min_evidence_count"]
        ), f"[{item['id']}] Expected at least {assertions['min_evidence_count']} evidence items, got {len(res.evidence)}"

    if "max_evidence_count" in assertions:
        assert (
            len(res.evidence) <= assertions["max_evidence_count"]
        ), f"[{item['id']}] Expected at most {assertions['max_evidence_count']} evidence items, got {len(res.evidence)}"

    if "evidence_status" in assertions:
        expected_status = assertions["evidence_status"]
        matching = [ev for ev in res.evidence if ev.status == expected_status]
        assert (
            len(matching) >= 1
        ), f"[{item['id']}] Expected at least one evidence item with status '{expected_status}', found {[e.status for e in res.evidence]}"

    # 5. Calculation step assertions
    if assertions.get("has_calculations", False):
        assert (
            len(res.calculations) >= 1
        ), f"[{item['id']}] Expected at least 1 calculation step, got {len(res.calculations)}"

    # 6. UI Action assertions
    if "min_ui_actions" in assertions:
        assert (
            len(res.ui_actions) >= assertions["min_ui_actions"]
        ), f"[{item['id']}] Expected at least {assertions['min_ui_actions']} UI actions, got {len(res.ui_actions)}"

    if "max_ui_actions" in assertions:
        assert (
            len(res.ui_actions) <= assertions["max_ui_actions"]
        ), f"[{item['id']}] Expected at most {assertions['max_ui_actions']} UI actions, got {len(res.ui_actions)}"

    if "action_type" in assertions:
        assert (
            len(res.ui_actions) >= 1 and res.ui_actions[0].type == assertions["action_type"]
        ), f"[{item['id']}] Expected UI action type '{assertions['action_type']}'"

    # 7. Download item assertions
    if "min_downloads" in assertions:
        assert (
            len(res.downloads) >= assertions["min_downloads"]
        ), f"[{item['id']}] Expected at least {assertions['min_downloads']} download items, got {len(res.downloads)}"

    if "max_downloads" in assertions:
        assert (
            len(res.downloads) <= assertions["max_downloads"]
        ), f"[{item['id']}] Expected at most {assertions['max_downloads']} download items, got {len(res.downloads)}"

    if "download_format" in assertions:
        assert (
            len(res.downloads) >= 1 and res.downloads[0].format == assertions["download_format"]
        ), f"[{item['id']}] Expected download format '{assertions['download_format']}'"

    if "download_url_contains" in assertions:
        assert (
            len(res.downloads) >= 1 and assertions["download_url_contains"] in res.downloads[0].url
        ), f"[{item['id']}] Expected download URL to contain '{assertions['download_url_contains']}'"

    # 8. Mandatory scientific disclaimer verification
    if assertions.get("require_disclaimer", False):
        assert (
            "burned area or unique wildfire events" in res.answer.lower()
        ), f"[{item['id']}] Mandatory scientific disclaimer missing from answer."


def test_evaluation_dataset_aggregate_score(orchestrator: OrchestratorAgent):
    """Aggregate benchmark evaluating the full evaluation dataset and calculating passing accuracy."""
    total = len(EVAL_CASES)
    passed = 0
    failures: list[str] = []

    for item in EVAL_CASES:
        try:
            req = ChatRequest(
                message=item["question"],
                region=item.get("region", "sri-lanka"),
            )
            res = orchestrator.process(req)
            assert res.intent == item["expected_intent"]
            assertions = item.get("assertions", {})
            for text in assertions.get("contains_text", []):
                assert text.lower() in res.answer.lower()
            for text in assertions.get("disallowed_text", []):
                assert text.lower() not in res.answer.lower()
            passed += 1
        except Exception as e:
            failures.append(f"{item['id']} ({item['category']}): {e}")

    accuracy = (passed / total) * 100.0
    print(f"\n==================================================")
    print(f"Evaluation Dataset Benchmark: {passed}/{total} passed ({accuracy:.1f}%)")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  - {f}")
    print(f"==================================================")

    assert accuracy == 100.0, f"Evaluation benchmark accuracy fell below 100%: {failures}"
