"""Web search tools using the ddgs package with DuckDuckGo-branded results."""

from __future__ import annotations

from typing import Any, Dict, List

from ddgs import DDGS


def _normalize_result(item: Dict[str, Any]) -> Dict[str, str]:
    return {
        "title": str(item.get("title") or "").strip(),
        "snippet": str(item.get("body") or item.get("snippet") or "").strip(),
        "url": str(item.get("href") or item.get("url") or "").strip(),
    }


def duckduckgo_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Perform a web search using ddgs and return normalized results."""
    try:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return {"error": "Query is required"}

        try:
            normalized_max_results = int(max_results)
        except (TypeError, ValueError):
            normalized_max_results = 5
        normalized_max_results = max(1, min(normalized_max_results, 10))

        raw_results: List[Dict[str, Any]] = list(
            DDGS().text(normalized_query, max_results=normalized_max_results)
        )

        results = []
        for item in raw_results:
            normalized_item = _normalize_result(item)
            if normalized_item["title"] and normalized_item["url"]:
                results.append(normalized_item)

        if not results:
            return {"message": "No results found.", "results": []}

        return {"results": results}
    except Exception as e:
        return {"error": f"Search error: {str(e)}"}
