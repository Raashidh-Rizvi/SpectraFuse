"""Unit tests for Phase 6 multi-provider LLM integration and graceful fallback."""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.agents.model_provider import (
    BaseModelProvider,
    FallbackModelProvider,
    GeminiModelProvider,
    GroqModelProvider,
    MockModelProvider,
    ModelResponse,
    OpenAIModelProvider,
    ProviderAPIError,
    get_model_provider,
)


def test_tc_p01_mock_model_provider():
    """TC-P01: MockModelProvider resolves queries deterministically without network calls."""
    provider = MockModelProvider()
    res = provider.generate([{"role": "user", "content": "What was the fire activity in August 2021?"}])
    assert isinstance(res, ModelResponse)
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0]["name"] == "get_monthly_activity"
    assert res.tool_calls[0]["arguments"]["start_month"] == "2021-08"


def test_tc_p01_groq_model_provider_success():
    """TC-P01: GroqModelProvider formats OpenAI-compatible tools and parses tool calls."""
    provider = GroqModelProvider(api_key="gsk_mock_test_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Checking data...",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_monthly_activity",
                                "arguments": '{"region": "sri-lanka", "start_month": "2021-08"}',
                            },
                        }
                    ],
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        tools = [{"name": "get_monthly_activity", "description": "query", "parameters": {}}]
        res = provider.generate([{"role": "user", "content": "test"}], tools=tools)

        assert res.content == "Checking data..."
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0]["name"] == "get_monthly_activity"
        assert res.tool_calls[0]["arguments"]["start_month"] == "2021-08"
        assert mock_post.called


def test_tc_p01_gemini_model_provider_success():
    """TC-P01: GeminiModelProvider formats functionDeclarations and parses functionCall."""
    provider = GeminiModelProvider(api_key="mock_gemini_test_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "get_monthly_activity",
                                "args": {"region": "sri-lanka", "start_month": "2021-08"},
                            }
                        }
                    ],
                    "role": "model",
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        tools = [{"name": "get_monthly_activity", "description": "query", "parameters": {}}]
        res = provider.generate([{"role": "user", "content": "test"}], tools=tools)

        assert len(res.tool_calls) == 1
        assert res.tool_calls[0]["name"] == "get_monthly_activity"
        assert res.tool_calls[0]["arguments"]["start_month"] == "2021-08"
        assert mock_post.called


def test_tc_p01_openai_model_provider_success():
    """TC-P01: OpenAIModelProvider parses standard OpenAI chat completions."""
    provider = OpenAIModelProvider(api_key="sk-mock-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Analyzing active fire trends.",
                    "tool_calls": [],
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp):
        res = provider.generate([{"role": "user", "content": "hello"}])
        assert res.content == "Analyzing active fire trends."
        assert len(res.tool_calls) == 0


def test_tc_p02_provider_fallback_on_429_or_500():
    """TC-P02: FallbackModelProvider catches HTTP 429/500/timeout and falls back to Mock."""
    groq = GroqModelProvider(api_key="gsk_mock_test_key", max_retries=1)
    fallback = MockModelProvider()
    resilient_provider = FallbackModelProvider(primary=groq, fallback=fallback)

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit exceeded"

    with patch("requests.post", return_value=mock_resp):
        # Even though primary returns 429, FallbackModelProvider transparently falls back to Mock
        res = resilient_provider.generate([{"role": "user", "content": "What was the fire activity in August 2021?"}])
        assert isinstance(res, ModelResponse)
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0]["name"] == "get_monthly_activity"


def test_tc_p02_gemini_fallback_with_mock_key():
    """TC-P02: Mock Gemini key automatically falls back to MockModelProvider without crashing."""
    # User's provided mock Gemini key
    gemini = GeminiModelProvider(api_key="mock_gemini_test_key", max_retries=0)
    resilient_provider = FallbackModelProvider(primary=gemini, fallback=MockModelProvider())

    # Simulate Google API returning HTTP 400 API_KEY_INVALID
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = '{"error": {"code": 400, "message": "API_KEY_INVALID"}}'

    with patch("requests.post", return_value=mock_resp):
        res = resilient_provider.generate([{"role": "user", "content": "Compare MODIS and VIIRS for 2020"}])
        assert isinstance(res, ModelResponse)
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0]["name"] == "compare_sensors"


def test_tc_p03_offline_mode_env():
    """TC-P03: If USE_MOCK_MODEL=true or LLM_PROVIDER=mock, get_model_provider returns MockModelProvider."""
    with patch.dict(os.environ, {"USE_MOCK_MODEL": "true", "LLM_PROVIDER": "mock"}):
        provider = get_model_provider()
        assert isinstance(provider, MockModelProvider)


def test_tc_p04_gemini_provider_factory_selection():
    """TC-P04: If LLM_PROVIDER=gemini and GEMINI_API_KEY is present, factory returns Fallback with Gemini."""
    with patch.dict(os.environ, {
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "mock_gemini_test_key",
        "USE_MOCK_MODEL": "false",
    }):
        provider = get_model_provider()
        assert isinstance(provider, FallbackModelProvider)
        assert isinstance(provider.primary, GeminiModelProvider)
        assert isinstance(provider.fallback, MockModelProvider)
