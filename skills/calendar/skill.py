"""
/calendar <action> [args]
  /calendar today           — today's events
  /calendar week            — this week's events
  /calendar free <date>     — find a free slot
  /calendar add <title> on <date> at <time>
"""

DESCRIPTION = "Read and create Google Calendar events"


def run(query: str = "", context: str = "") -> str:
    if not query:
        return (
            "Usage:\n"
            "  /calendar today\n"
            "  /calendar week\n"
            "  /calendar free <date>\n"
            "  /calendar add <title> on <date> at <time>"
        )

    import sys, re
    from pathlib import Path
    sys.path.insert(0, str(Path.home() / "cascade"))
    from cascade.calendar_agent import get_today, get_week, find_free_slot, create_event

    q = query.strip()

    if q == "today":
        return get_today()

    if q == "week":
        return get_week()

    if q.startswith("free "):
        return find_free_slot(q[5:].strip())

    if q.startswith("add "):
        rest = q[4:].strip()
        m = re.match(r"(.+?)\s+on\s+(.+?)\s+at\s+(.+)", rest, re.IGNORECASE)
        if m:
            return create_event(m.group(1).strip(), m.group(2).strip(), m.group(3).strip())
        return "Usage: /calendar add <title> on <date> at <time>"

    return get_today()
