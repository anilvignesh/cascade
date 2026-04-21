"""
/remind <text with date>
  /remind call Arjun tomorrow
  /remind follow up with Visa team Friday
  /remind submit report next week
  /remind list
"""

DESCRIPTION = "Set and list reminders (natural language dates)"


def run(query: str = "", context: str = "") -> str:
    if not query:
        return (
            "Usage:\n"
            "  /remind call Arjun tomorrow\n"
            "  /remind follow up Friday\n"
            "  /remind list"
        )

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.home() / "cascade"))
    from cascade.reminders import add, list_upcoming

    q = query.strip()

    if q == "list":
        return list_upcoming()

    return add(q)
