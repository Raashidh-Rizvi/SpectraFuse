from types import SimpleNamespace
from unittest.mock import Mock

from backend.agents import web_explanation
from backend.agents.schemas import ChatRequest, ChatResponse


def test_explanation_returns_only_provider_citations(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = Mock(return_value=Mock(status_code=200, **{
        "json.return_value": {
            "status": "completed",
            "output": [{"type": "message", "content": [{
                "type": "output_text",
                "text": "Would you like MODIS or VIIRS coverage?",
                "annotations": [
                    {"type": "url_citation", "url": "https://firms.modaps.eosdis.nasa.gov/", "title": "NASA FIRMS"},
                    {"type": "url_citation", "url": "javascript:alert(1)", "title": "Invalid link"},
                ],
            }]}],
        },
    }))
    monkeypatch.setattr(web_explanation.requests, "post", provider)
    archive_answer = ChatResponse(request_id="request", session_id="session", intent="general",
                                  answer="Archive answer", region="demo")

    result = web_explanation.explain(
        ChatRequest(message="Can you explain sensor coverage?", region="demo"),
        SimpleNamespace(turns=[]),
        archive_answer,
        lambda: {"monthly_rows": []},
    )

    assert result.answer == "Would you like MODIS or VIIRS coverage?"
    assert result.web_sources == [{"url": "https://firms.modaps.eosdis.nasa.gov/", "title": "NASA FIRMS"}]
    assert provider.call_args.kwargs["json"]["tools"] == [{"type": "web_search"}]

    provider.return_value.status_code = 429
    assert web_explanation.explain(ChatRequest(message="Explain coverage"),
                                   SimpleNamespace(turns=[]), archive_answer, lambda: None) is archive_answer
