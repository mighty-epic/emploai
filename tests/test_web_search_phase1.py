from types import SimpleNamespace

from cli.agent_tools import web_tools
from telegram_bot.telegram_unified_agent import _execute_web_search


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None, timeout=None):
        return self._response


def test_duckduckgo_search_parses_results_with_snippets(monkeypatch):
    html = """
    <html><body>
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Falpha">Alpha <b>Result</b></a>
      <div class="result__snippet">Alpha snippet with <b>bold</b> text.</div>
      <a class="result__a" href="https://example.com/beta">Beta Result</a>
      <a class="result__snippet">Beta snippet text.</a>
    </body></html>
    """

    monkeypatch.setattr(
        web_tools.httpx,
        "Client",
        lambda **kwargs: _FakeClient(_FakeResponse(html)),
    )

    result = web_tools.duckduckgo_search("emploai", max_results=5)

    assert len(result["results"]) == 2
    assert result["results"][0]["title"] == "Alpha Result"
    assert result["results"][0]["url"] == "https://example.com/alpha"
    assert result["results"][0]["snippet"] == "Alpha snippet with bold text."
    assert result["results"][1]["title"] == "Beta Result"
    assert result["results"][1]["url"] == "https://example.com/beta"


def test_duckduckgo_search_returns_error_for_non_200(monkeypatch):
    monkeypatch.setattr(
        web_tools.httpx,
        "Client",
        lambda **kwargs: _FakeClient(_FakeResponse("nope", status_code=503)),
    )

    result = web_tools.duckduckgo_search("emploai")

    assert result["error"] == "Search failed with status 503"


def test_telegram_web_search_formats_results(monkeypatch):
    monkeypatch.setattr(
        "telegram_bot.telegram_unified_agent.duckduckgo_search",
        lambda query, max_results=5: {
            "results": [
                {
                    "title": "Alpha Result",
                    "url": "https://example.com/alpha",
                    "snippet": "Alpha snippet",
                },
                {
                    "title": "Beta Result",
                    "url": "https://example.com/beta",
                    "snippet": "",
                },
            ]
        },
    )

    output = _execute_web_search(SimpleNamespace(), {"query": "emploai", "max_results": 2})

    assert "DuckDuckGo results for 'emploai':" in output
    assert "1. Alpha Result" in output
    assert "URL: https://example.com/alpha" in output
    assert "Snippet: Alpha snippet" in output
    assert "2. Beta Result" in output


def test_telegram_web_search_handles_empty_and_error(monkeypatch):
    monkeypatch.setattr(
        "telegram_bot.telegram_unified_agent.duckduckgo_search",
        lambda query, max_results=5: {"results": []},
    )
    assert _execute_web_search(SimpleNamespace(), {"query": "emploai"}) == (
        "No DuckDuckGo results found for 'emploai'."
    )

    monkeypatch.setattr(
        "telegram_bot.telegram_unified_agent.duckduckgo_search",
        lambda query, max_results=5: {"error": "timeout"},
    )
    assert _execute_web_search(SimpleNamespace(), {"query": "emploai"}) == (
        "DuckDuckGo search error for 'emploai': timeout"
    )
