"""Web search tools using DuckDuckGo."""

import httpx
from typing import Dict, Any, List
import re

def duckduckgo_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Perform a web search using DuckDuckGo's HTML interface.
    No API key required.
    """
    try:
        # Use DuckDuckGo HTML/Lite version for easier scraping without JS
        url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        
        with httpx.Client(follow_redirects=True, headers=headers) as client:
            response = client.get(url, timeout=10)
            
        if response.status_code != 200:
            return {"error": f"Search failed with status {response.status_code}"}
            
        # Parse results using regex (brittle but avoids additional dependencies like BeautifulSoup)
        # Results are usually in <a class="result__a" href="...">Title</a>
        # Snippets in <a class="result__snippet" ...>Snippet</a>
        
        matches = re.finditer(
            r'<a class="result__a" href="(?P<url>[^"]+)">(?P<title>.*?)</a>.*?<a class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
            response.text,
            re.DOTALL
        )
        
        results = []
        for match in matches:
            # Clean HTML tags from title and snippet
            title = re.sub(r'<[^>]+>', '', match.group('title')).strip()
            snippet = re.sub(r'<[^>]+>', '', match.group('snippet')).strip()
            url = match.group('url')
            
            # DDG internal links can be prefixed with /l/?kh=-1&uddg=
            if "uddg=" in url:
                url = url.split("uddg=")[1].split("&")[0]
                import urllib.parse
                url = urllib.parse.unquote(url)
            
            results.append({
                "title": title,
                "snippet": snippet,
                "url": url
            })
            
            if len(results) >= max_results:
                break
                
        if not results:
            return {"message": "No results found.", "results": []}
            
        return {"results": results}
        
    except Exception as e:
        return {"error": f"Search error: {str(e)}"}

# You can add more web tools here (e.g. read_url)
