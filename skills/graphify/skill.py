"""
/graphify — convert any input into a MemPalace knowledge graph entry.
Usage: /graphify <anything to remember>
"""

import subprocess

DESCRIPTION = "Save any input as a knowledge graph entry in MemPalace"


def run(query: str, context: str = "") -> str:
    content = query.strip()
    if not content:
        return "Nothing to graphify."
    try:
        subprocess.run(
            ["mempalace", "kg-add", "--content", content],
            capture_output=True, timeout=10
        )
        return f"Saved to knowledge graph: {content[:80]}"
    except Exception as e:
        return f"graphify error: {e}"
