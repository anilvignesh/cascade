"""
/news — fetch latest fintech/stablecoin/RBI/LLM news.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".jarvis"))

DESCRIPTION = "Fetch latest fintech and payments news"


def run(query: str = "", context: str = "") -> str:
    try:
        from agents.fintech_monitor import fetch
        data    = fetch(force=bool(query and "refresh" in query.lower()))
        cats    = data.get("categories", {})
        updated = data.get("updated", "")
        total   = sum(len(v) for v in cats.values())
        if not total:
            return "No news cached. Try: /news refresh"
        labels = {"fintech": "Fintech", "stablecoin": "Stablecoins",
                  "rbi": "RBI", "llm": "LLM Releases", "nium": "Target Cos"}
        lines = [f"News · {updated}\n"]
        for cat, items in cats.items():
            if not items:
                continue
            lines.append(f"{labels.get(cat, cat.upper())}")
            for item in items[:2]:
                lines.append(f"  · {item.get('title','')}")
                if item.get("summary"):
                    lines.append(f"    {item['summary'][:100]}")
        return "\n".join(lines)
    except Exception as e:
        return f"news skill error: {e}"
