"""
/system — quick laptop health check (RAM, disk, Ollama).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".jarvis"))

DESCRIPTION = "Quick laptop health check — RAM, disk, Ollama"


def run(query: str = "", context: str = "") -> str:
    try:
        from agents.system_agent import fetch
        d    = fetch(force=True)
        ram  = d.get("ram", {})
        disk = d.get("disk", {})
        ol   = d.get("ollama", {})
        lines = [
            f"RAM:    {ram.get('available_gb','?')} GB free  ({ram.get('used_pct','?')}% used)",
            f"Disk:   {disk.get('free','?')} free of {disk.get('total','?')}",
            f"Ollama: {ol.get('status','?')}  [{', '.join(ol.get('models',[]))}]",
            f"Apt:    {d.get('apt','?')}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"system skill error: {e}"
