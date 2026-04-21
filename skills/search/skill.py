"""
Web search skill — Tavily API (recommended) or DuckDuckGo (fallback, no key needed).

Setup (optional, for better results):
  Add to ~/.cascade.env:
  TAVILY_API_KEY=your_key

Usage:
  /search what is SWIFT gpi
  /search latest RBI PA-CB guidelines
"""

import os, urllib.request, urllib.parse, json
from pathlib import Path

DESCRIPTION = "Search the web — Tavily (if key set) or DuckDuckGo fallback"

_ENV_FILE = Path.home() / ".cascade.env"


def _load_env():
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _tavily(query: str) -> str:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return ""

    payload = json.dumps({
        "api_key":             api_key,
        "query":               query,
        "search_depth":        "basic",
        "include_answer":      True,
        "include_raw_content": False,
        "max_results":         5,
    }).encode()

    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    parts = []
    if data.get("answer"):
        parts.append(f"**Answer:** {data['answer']}\n")

    for r in data.get("results", [])[:5]:
        title   = r.get("title", "")
        url     = r.get("url", "")
        content = r.get("content", "")[:300]
        parts.append(f"**{title}**\n{content}\n{url}")

    return "\n\n".join(parts)


def _ddg(query: str) -> str:
    """DuckDuckGo instant answer API — no key, limited results."""
    params = urllib.parse.urlencode({"q": query, "format": "json", "no_html": "1"})
    req    = urllib.request.Request(
        f"https://api.duckduckgo.com/?{params}",
        headers={"User-Agent": "cascade/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    parts = []
    if data.get("AbstractText"):
        parts.append(f"**{data.get('Heading', '')}**\n{data['AbstractText']}")
        if data.get("AbstractURL"):
            parts.append(data["AbstractURL"])

    for r in data.get("RelatedTopics", [])[:4]:
        if isinstance(r, dict) and r.get("Text"):
            parts.append(f"• {r['Text'][:200]}")

    return "\n\n".join(parts) if parts else "No results found."


def run(query: str, context: str = "") -> str:
    _load_env()

    try:
        result = _tavily(query)
        if result:
            return result
    except Exception:
        pass

    try:
        return _ddg(query)
    except Exception as e:
        return f"Search error: {e}"
