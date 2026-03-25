"""Web search tools using DuckDuckGo."""

from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any, Dict

import httpx


_RESULT_LINK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_SNIPPET_RE = re.compile(
    r'<(?:a|div|span)[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</(?:a|div|span)>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_html_fragment(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _decode_result_url(url: str) -> str:
    if "uddg=" not in url:
        return html.unescape(url)

    parsed = urllib.parse.urlparse(url)
    uddg_values = urllib.parse.parse_qs(parsed.query).get("uddg")
    if uddg_values:
        return urllib.parse.unquote(uddg_values[0])

    return urllib.parse.unquote(url.split("uddg=", 1)[1].split("&", 1)[0])


def duckduckgo_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Perform a web search using DuckDuckGo's HTML interface."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }

        with httpx.Client(follow_redirects=True, headers=headers) as client:
            response = client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                timeout=10,
            )

        if response.status_code != 200:
            return {"error": f"Search failed with status {response.status_code}"}

        text = response.text
        link_matches = list(_RESULT_LINK_RE.finditer(text))
        results = []

        for index, match in enumerate(link_matches):
            next_start = link_matches[index + 1].start() if index + 1 < len(link_matches) else len(text)
            trailing_html = text[match.end():next_start]
            snippet_match = _SNIPPET_RE.search(trailing_html)

            title = _clean_html_fragment(match.group("title"))
            url = _decode_result_url(match.group("url"))
            snippet = _clean_html_fragment(snippet_match.group("snippet")) if snippet_match else ""

            if not title or not url:
                continue

            results.append({
                "title": title,
                "snippet": snippet,
                "url": url,
            })

            if len(results) >= max_results:
                break

        if not results:
            return {"message": "No results found.", "results": []}

        return {"results": results}

    except Exception as e:
        return {"error": f"Search error: {str(e)}"}
