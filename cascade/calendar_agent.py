"""
Calendar agent — read events, create meetings via Google Calendar MCP.
Requires Google Calendar MCP authenticated in Claude Code first:
  1. Run `claude` in terminal
  2. Type /mcp → select "claude.ai Google Calendar" → complete OAuth
"""

import subprocess
from pathlib import Path
from datetime import datetime

CLAUDE_BIN     = str(Path.home() / ".local" / "bin" / "claude")
CALENDAR_TOOLS = (
    "mcp__claude_ai_Google_Calendar__authenticate,"
    "mcp__claude_ai_Google_Calendar__complete_authentication"
)


def _run(prompt: str) -> str:
    result = subprocess.run(
        [CLAUDE_BIN, "-p", prompt,
         "--allowedTools", CALENDAR_TOOLS,
         "--dangerously-skip-permissions"],
        capture_output=True, text=True, timeout=120
    )
    return result.stdout.strip() or result.stderr.strip()


def get_today() -> str:
    today = datetime.now().strftime("%A %d %B %Y")
    return _run(
        f"Use Google Calendar MCP to get today's events ({today}). "
        f"List each event: time, title, attendees if any. "
        f"If nothing today, check tomorrow too. Be concise."
    )


def get_week() -> str:
    return _run(
        "Use Google Calendar MCP to get this week's events. "
        "Group by day. Time + title only."
    )


def create_event(title: str, date: str, time: str,
                 duration: str = "1 hour", attendees: str = "") -> str:
    attendee_str = f"Attendees: {attendees}" if attendees else ""
    return _run(
        f"Use Google Calendar MCP to create an event.\n"
        f"Title: {title}\nDate: {date}\nTime: {time}\n"
        f"Duration: {duration}\n{attendee_str}\n"
        f"Confirm when created."
    )


def find_free_slot(date: str, duration: str = "1 hour") -> str:
    return _run(
        f"Use Google Calendar MCP to find a free {duration} slot on {date}. "
        f"Return the best available time."
    )
