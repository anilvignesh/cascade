"""
/jobs — fetch latest job listings from the local job hunter agent cache.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".jarvis"))

DESCRIPTION = "Fetch latest job listings from local cache"


def run(query: str = "", context: str = "") -> str:
    try:
        from agents.job_hunter import fetch
        data  = fetch(force=bool(query and "refresh" in query.lower()))
        jobs  = data.get("jobs", [])
        updated = data.get("updated", "")
        if not jobs:
            return "No jobs cached. Try: /jobs refresh"
        lines = [f"Jobs · {updated}\n"]
        for j in jobs[:8]:
            dot = "●" if j.get("fit") == "high" else "○"
            lines.append(f"{dot} {j.get('title','')} — {j.get('company','')} ({j.get('location','')})")
            if j.get("url"):
                lines.append(f"  {j['url'][:70]}")
        return "\n".join(lines)
    except Exception as e:
        return f"jobs skill error: {e}"
