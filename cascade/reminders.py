"""
Persistent reminders — stored in MemPalace, checked every hour by cron.
Natural language: "remind me Friday", "follow up with Arjun next week"
"""

import json, os, re, subprocess
from datetime import datetime, timedelta
from pathlib import Path


def _send_telegram(message: str):
    env_file = Path.home() / ".cascade.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    token   = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    import urllib.request, urllib.parse
    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": message, "parse_mode": "Markdown"
    }).encode()
    urllib.request.urlopen(url, data=data, timeout=10)


def _parse_date(text: str) -> str | None:
    """Parse natural language date to YYYY-MM-DD."""
    text = text.lower().strip()
    now  = datetime.now()

    if "today"    in text: return now.strftime("%Y-%m-%d")
    if "tomorrow" in text: return (now + timedelta(days=1)).strftime("%Y-%m-%d")

    days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    for i, day in enumerate(days):
        if day in text:
            diff = (i - now.weekday()) % 7 or 7
            return (now + timedelta(days=diff)).strftime("%Y-%m-%d")

    if "next week" in text:
        return (now + timedelta(weeks=1)).strftime("%Y-%m-%d")
    if "in 2 days" in text or "2 days" in text:
        return (now + timedelta(days=2)).strftime("%Y-%m-%d")
    if "in 3 days" in text or "3 days" in text:
        return (now + timedelta(days=3)).strftime("%Y-%m-%d")

    # Try YYYY-MM-DD
    m = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if m: return m.group()

    return None


def add(text: str, when: str = "") -> str:
    """Add a reminder. Returns confirmation."""
    date = _parse_date(when or text) or datetime.now().strftime("%Y-%m-%d")
    entry = f"[reminder] due:{date} | {text}"
    try:
        subprocess.run(
            ["mempalace", "add", "--content", entry, "--tags", "reminder,cascade"],
            capture_output=True, timeout=8
        )
        return f"Reminder set for {date}: {text}"
    except Exception as e:
        return f"Could not save reminder: {e}"


def check_due():
    """Called by cron — check for due reminders and send Telegram alerts."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        r = subprocess.run(
            ["mempalace", "search", f"reminder due:{today}", "--limit", "10"],
            capture_output=True, text=True, timeout=8
        )
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and "reminder" in l.lower() and today in l]
        for line in lines:
            _send_telegram(f"⏰ *Reminder*\n{line.replace(f'[reminder] due:{today} | ', '')}")
    except Exception as e:
        print(f"Reminder check error: {e}")


def list_upcoming() -> str:
    """Return upcoming reminders as text."""
    try:
        r = subprocess.run(
            ["mempalace", "search", "reminder due", "--limit", "10"],
            capture_output=True, text=True, timeout=8
        )
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and "reminder" in l.lower() and "due:" in l]
        if not lines:
            return "No upcoming reminders."
        return "\n".join(lines[:8])
    except Exception:
        return "Could not fetch reminders."
