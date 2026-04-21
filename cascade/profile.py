"""
Loads user profile from MemPalace at session start.
Cached for the session — not re-fetched on every query.
"""

import subprocess

_cache: str = ""


def load() -> str:
    global _cache
    if _cache:
        return _cache
    try:
        r = subprocess.run(
            ["mempalace", "search", "cascade user profile", "--limit", "1"],
            capture_output=True, text=True, timeout=8
        )
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and not l.startswith(("Search", "===", "---"))]
        _cache = "\n".join(lines)[:1200]
    except Exception:
        _cache = ""
    return _cache
