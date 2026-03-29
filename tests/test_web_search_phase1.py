from types import SimpleNamespace

from cli.agent_tools import web_tools
from telegram_bot.telegram_unified_agent import _execute_web_search


class _FakeDDGS:
    def __init__(self, results=None, error=None):
        self._results = results or []
        self._error = error

    def text(self, query, max_results=5):
        if self._error:
            raise self._error
        return self._results[:max_results]


def test_duckduckgo_search_normalizes_ddgs_results(monkeypatch):
    monkeypatch.setattr(
        web_tools,
        "DDGS",
        lambda: _FakeDDGS(
            [
                {
                    "title": "Alpha Result",
                    "href": "https://example.com/alpha",
                    "body": "Alpha snippet",
                },
                {
                    "title": "Beta Result",
                    "url": "https://example.com/beta",
                    "snippet": "Beta snippet",
                },
            ]
        ),
    )

    result = web_tools.duckduckgo_search("emploai", max_results=5)

    assert len(result["results"]) == 2
    assert result["results"][0] == {
        "title": "Alpha Result",
        "url": "https://example.com/alpha",
        "snippet": "Alpha snippet",
    }
    assert result["results"][1] == {
        "title": "Beta Result",
        "url": "https://example.com/beta",
        "snippet": "Beta snippet",
    }


def test_duckduckgo_search_returns_error_when_ddgs_fails(monkeypatch):
    monkeypatch.setattr(
        web_tools,
        "DDGS",
        lambda: _FakeDDGS(error=RuntimeError("blocked")),
    )

    result = web_tools.duckduckgo_search("emploai")

    assert result["error"] == "Search error: blocked"


def test_duckduckgo_search_requires_query():
    result = web_tools.duckduckgo_search("   ")

    assert result["error"] == "Query is required"


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
