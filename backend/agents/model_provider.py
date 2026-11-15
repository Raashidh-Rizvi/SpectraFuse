"""Model provider abstraction supporting Mock, Groq, Gemini, and OpenAI with automated fallback."""

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from dotenv import load_dotenv
import requests

from backend.fire import ROOT

logger = logging.getLogger("agents.model_provider")


class ProviderAPIError(Exception):
    """Exception raised when an upstream LLM API fails or is unavailable."""

    def __init__(self, provider: str, status_code: int | None, message: str):
        super().__init__(f"[{provider}] HTTP {status_code}: {message}")
        self.provider = provider
        self.status_code = status_code
        self.message = message


class ModelResponse:
    """Normalized response from any language model provider."""

    def __init__(self, content: str, tool_calls: list[dict[str, Any]] | None = None, raw: Any = None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.raw = raw

    def __repr__(self) -> str:
        return f"<ModelResponse content_len={len(self.content)} tool_calls={len(self.tool_calls)}>"


class BaseModelProvider(ABC):
    """Abstract interface for all model providers."""

    @abstractmethod
    def generate(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> ModelResponse:
        """Generate a response or tool call given message history and optional tools."""
        pass


class MockModelProvider(BaseModelProvider):
    """Deterministic, zero-cost, offline model provider for tests and local fallback."""

    MONTH_MAP = {
        "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
        "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
        "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    }

    def generate(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> ModelResponse:
        user_message = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_message = m.get("content", "")
                break

        low = user_message.lower().strip()

        # Check for injection or secret extraction attempts
        if any(w in low for w in ("ignore", "system prompt", "firm", "firms_map_key", "api_key", "password", "secret", "env")):
            return ModelResponse(
                content="I cannot provide server credentials, private keys, or override my instructions. I can only assist with active-fire analytics."
            )

        # Map / Hotspot request
        if "hotspot" in low or "map" in low or "bounding box" in low or "bbox" in low:
            date_matches = re.findall(r"\b20\d\d-\d\d-\d\d\b", low)
            start = date_matches[0] if len(date_matches) >= 1 else "2022-03-01"
            end = date_matches[1] if len(date_matches) >= 2 else "2022-03-10"
            bbox_match = re.search(r"(-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*,-?\d+\.?\d*)", low)
            bbox = bbox_match.group(1) if bbox_match else None
            return ModelResponse(
                content="Generating map layers.",
                tool_calls=[{
                    "name": "get_map_layers_action",
                    "arguments": {"region": "sri-lanka", "start_date": start, "end_date": end, "bbox": bbox},
                }]
            )

        # Export request
        if "download" in low or "export" in low or "csv" in low:
            year_match = re.search(r"\b(20\d\d)\b", low)
            year = int(year_match.group(1)) if year_match else 2022
            return ModelResponse(
                content="Preparing your CSV download.",
                tool_calls=[{
                    "name": "generate_export_reference",
                    "arguments": {"region": "sri-lanka", "year": year, "export_type": "monthly"},
                }]
            )

        # Anomaly / Seasonal departure request
        if any(w in low for w in ("unusual", "anomaly", "departure", "normal")):
            year_match = re.search(r"\b(20\d\d)\b", low)
            year = int(year_match.group(1)) if year_match else 2023
            month = 3
            for name, num in self.MONTH_MAP.items():
                if name in low:
                    month = num
                    break
            return ModelResponse(
                content="Evaluating seasonal anomaly.",
                tool_calls=[{
                    "name": "get_seasonal_departure",
                    "arguments": {"region": "sri-lanka", "year": year, "month": month, "sensor_basis": "harmonized"},
                }]
            )

        # Sensor comparison
        if "compare" in low or "comparison" in low:
            year_match = re.search(r"\b(20\d\d)\b", low)
            start_m = f"{year_match.group(1)}-01" if year_match else "2020-01"
            end_m = f"{year_match.group(1)}-12" if year_match else "2020-12"
            return ModelResponse(
                content="Comparing satellite sensors.",
                tool_calls=[{
                    "name": "compare_sensors",
                    "arguments": {"region": "sri-lanka", "start_month": start_m, "end_month": end_m},
                }]
            )

        # Calibration question
        if any(w in low for w in ("multiplier", "calibration", "holdout", "factor", "how reliable", "estimate")):
            return ModelResponse(
                content="Checking calibration details.",
                tool_calls=[{
                    "name": "get_calibration_summary",
                    "arguments": {"region": "sri-lanka"},
                }]
            )

        # Coverage question
        if "incomplete" in low or "blank" in low or "missing" in low:
            return ModelResponse(
                content="A month contributes a sensor total only when every calendar day has a processed daily partition. Missing data means daily satellite partitions are unavailable, which is distinct from zero observed detections."
            )

        # Methodology question
        if any(w in low for w in ("difference between", "what is modis", "what is viirs", "resolution", "burned area", "unique fire")):
            return ModelResponse(
                content="MODIS has a 1 km resolution at nadir and operates on Terra and Aqua. VIIRS (Suomi-NPP and NOAA-20) has a 375 m resolution, detecting smaller and lower-intensity fires. Hotspot detection counts represent satellite thermal observations, not burned area or unique wildfire events."
            )

        # Default: Monthly activity inquiry
        year_match = re.search(r"\b(20\d\d)\b", low)
        year = int(year_match.group(1)) if year_match else 2021
        month = 8
        for name, num in self.MONTH_MAP.items():
            if name in low:
                month = num
                break
        target_month = f"{year:04d}-{month:02d}"

        return ModelResponse(
            content="Checking monthly fire activity.",
            tool_calls=[{
                "name": "get_monthly_activity",
                "arguments": {"region": "sri-lanka", "start_month": target_month, "end_month": target_month},
            }]
        )


class GroqModelProvider(BaseModelProvider):
    """GroqCloud inference provider with OpenAI-compatible tool calling."""

    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile", timeout_sec: float = 15.0, max_retries: int = 2):
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries

    def generate(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> ModelResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
        }

        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(self.API_URL, headers=headers, json=payload, timeout=self.timeout_sec)
                if resp.status_code == 200:
                    data = resp.json()
                    choice = data.get("choices", [{}])[0]
                    msg = choice.get("message", {})
                    content = msg.get("content") or ""
                    raw_tool_calls = msg.get("tool_calls") or []

                    tool_calls = []
                    for tc in raw_tool_calls:
                        fn = tc.get("function", {})
                        fn_name = fn.get("name")
                        fn_args_raw = fn.get("arguments", "{}")
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                        tool_calls.append({"name": fn_name, "arguments": fn_args})

                    return ModelResponse(content=content, tool_calls=tool_calls, raw=data)

                # Rate limiting or temporary server error: retry with backoff
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(0.3 * (2 ** attempt))
                    continue

                raise ProviderAPIError("Groq", resp.status_code, resp.text[:300])

            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.3 * (2 ** attempt))
                    continue

        raise ProviderAPIError("Groq", None, str(last_error or "Network failure"))


class GeminiModelProvider(BaseModelProvider):
    """Google Gemini language model provider supporting standard tool schemas."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", timeout_sec: float = 15.0, max_retries: int = 2):
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries

    def generate(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> ModelResponse:
        endpoint = f"{self.BASE_URL}/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        # Format messages into Gemini contents format
        contents = []
        system_instruction_parts = []
        for m in messages:
            role = m.get("role")
            text = m.get("content", "")
            if role == "system":
                system_instruction_parts.append({"text": text})
            else:
                gemini_role = "model" if role == "assistant" else "user"
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": text}],
                })

        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Hello"}]})

        payload: dict[str, Any] = {
            "contents": contents,
        }

        if system_instruction_parts:
            payload["systemInstruction"] = {"parts": system_instruction_parts}

        if tools:
            payload["tools"] = [{
                "functionDeclarations": [
                    {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                    }
                    for t in tools
                ]
            }]

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout_sec)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        return ModelResponse(content="")

                    first_cand = candidates[0]
                    content_obj = first_cand.get("content", {})
                    parts = content_obj.get("parts", [])

                    content_text = ""
                    tool_calls = []
                    for part in parts:
                        if "text" in part:
                            content_text += part["text"]
                        if "functionCall" in part:
                            fc = part["functionCall"]
                            tool_calls.append({
                                "name": fc.get("name"),
                                "arguments": fc.get("args") or {},
                            })

                    return ModelResponse(content=content_text, tool_calls=tool_calls, raw=data)

                # Rate limiting or temporary server error: retry with backoff
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(0.3 * (2 ** attempt))
                    continue

                raise ProviderAPIError("Gemini", resp.status_code, resp.text[:300])

            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.3 * (2 ** attempt))
                    continue

        raise ProviderAPIError("Gemini", None, str(last_error or "Network failure"))


class OpenAIModelProvider(BaseModelProvider):
    """OpenAI API provider with function calling."""

    API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout_sec: float = 15.0, max_retries: int = 2):
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries

    def generate(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> ModelResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
        }

        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(self.API_URL, headers=headers, json=payload, timeout=self.timeout_sec)
                if resp.status_code == 200:
                    data = resp.json()
                    choice = data.get("choices", [{}])[0]
                    msg = choice.get("message", {})
                    content = msg.get("content") or ""
                    raw_tool_calls = msg.get("tool_calls") or []

                    tool_calls = []
                    for tc in raw_tool_calls:
                        fn = tc.get("function", {})
                        fn_name = fn.get("name")
                        fn_args_raw = fn.get("arguments", "{}")
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                        tool_calls.append({"name": fn_name, "arguments": fn_args})

                    return ModelResponse(content=content, tool_calls=tool_calls, raw=data)

                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(0.3 * (2 ** attempt))
                    continue

                raise ProviderAPIError("OpenAI", resp.status_code, resp.text[:300])

            except (requests.RequestException, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.3 * (2 ** attempt))
                    continue

        raise ProviderAPIError("OpenAI", None, str(last_error or "Network failure"))


class FallbackModelProvider(BaseModelProvider):
    """Resilient proxy executing primary provider with transparent fallback to offline MockModelProvider."""

    def __init__(self, primary: BaseModelProvider, fallback: BaseModelProvider | None = None):
        self.primary = primary
        self.fallback = fallback or MockModelProvider()

    def generate(self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None = None) -> ModelResponse:
        try:
            return self.primary.generate(messages, tools)
        except Exception as err:
            logger.warning(
                f"Primary model provider {self.primary.__class__.__name__} failed ({type(err).__name__}: {err}). "
                f"Gracefully falling back to {self.fallback.__class__.__name__}."
            )
            return self.fallback.generate(messages, tools)


def get_model_provider() -> BaseModelProvider:
    """Factory selecting the configured provider or defaulting to MockModelProvider with fallback."""
    load_dotenv(ROOT / ".env")
    provider_name = os.getenv("LLM_PROVIDER", "").lower().strip()
    use_mock = os.getenv("USE_MOCK_MODEL", "").lower() in ("true", "1")

    if use_mock or provider_name == "mock":
        return MockModelProvider()

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    # Priority 1: Explicit provider specified in LLM_PROVIDER
    if provider_name == "gemini" and gemini_key:
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
        primary = GeminiModelProvider(api_key=gemini_key, model=model)
        return FallbackModelProvider(primary=primary, fallback=MockModelProvider())

    if provider_name == "groq" and groq_key:
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        primary = GroqModelProvider(api_key=groq_key, model=model)
        return FallbackModelProvider(primary=primary, fallback=MockModelProvider())

    if provider_name == "openai" and openai_key:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        primary = OpenAIModelProvider(api_key=openai_key, model=model)
        return FallbackModelProvider(primary=primary, fallback=MockModelProvider())

    # Priority 2: Auto-detect available keys if provider not explicitly set
    if gemini_key and not groq_key:
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
        primary = GeminiModelProvider(api_key=gemini_key, model=model)
        return FallbackModelProvider(primary=primary, fallback=MockModelProvider())

    if groq_key:
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        primary = GroqModelProvider(api_key=groq_key, model=model)
        return FallbackModelProvider(primary=primary, fallback=MockModelProvider())

    if openai_key:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        primary = OpenAIModelProvider(api_key=openai_key, model=model)
        return FallbackModelProvider(primary=primary, fallback=MockModelProvider())

    return MockModelProvider()
