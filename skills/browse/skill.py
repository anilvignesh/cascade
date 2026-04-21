"""
/browse <url or search query> — open a URL or search the web.
Examples:
  /browse https://news.ycombinator.com
  /browse latest fintech news
  /browse swiggy.com menu biryani bangalore
"""

DESCRIPTION = "Browse a URL or search the web"


def run(query: str = "", context: str = "") -> str:
    if not query:
        return "Usage: /browse <url or search query>"

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.home() / "cascade"))
    from cascade.browser import browse, search

    if query.startswith("http"):
        content = browse(query)
        return f"[{query}]\n\n{content[:2000]}"
    else:
        return search(query)
