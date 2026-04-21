"""
Morning brief — runs at 7am via cron, pushes to Telegram.
Covers: calendar, inbox highlights, job alerts, top news, reminders.
"""

import os, sys, urllib.request, urllib.parse, json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".jarvis"))


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
        print(message)
        return

    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "Markdown",
    }).encode()
    urllib.request.urlopen(url, data=data, timeout=10)


def _get_calendar() -> str:
    try:
        from cascade.calendar_agent import get_today
        return get_today()
    except Exception:
        return ""


def _get_inbox() -> str:
    try:
        from cascade.email_agent import read_inbox
        return read_inbox(limit=3)
    except Exception:
        return ""


def _get_jobs() -> str:
    try:
        from agents.job_hunter import fetch
        data = fetch()
        jobs = [j for j in data.get("jobs", []) if j.get("fit") == "high"][:3]
        if not jobs:
            return ""
        lines = []
        for j in jobs:
            lines.append(f"• [{j.get('title','')} @ {j.get('company','')}]({j.get('url','')})")
        return "\n".join(lines)
    except Exception:
        return ""


def _get_news() -> str:
    try:
        from agents.fintech_monitor import fetch
        data  = fetch()
        cats  = data.get("categories", {})
        items = []
        for cat_items in cats.values():
            items.extend(cat_items[:1])
        lines = [f"• {i.get('title','')}" for i in items[:4]]
        return "\n".join(lines)
    except Exception:
        return ""


def _get_reminders() -> str:
    try:
        import subprocess
        r = subprocess.run(
            ["mempalace", "search", "reminder due today", "--limit", "3"],
            capture_output=True, text=True, timeout=8
        )
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and not l.startswith(("Search", "===", "---"))]
        return "\n".join(lines[:3])
    except Exception:
        return ""


def run():
    now      = datetime.now()
    greeting = "Good morning" if now.hour < 12 else "Good afternoon"
    date_str = now.strftime("%A, %d %B %Y")

    sections = [f"*{greeting}, Anil* — {date_str}\n"]

    cal = _get_calendar()
    if cal:
        sections.append(f"*📅 Today*\n{cal}")

    inbox = _get_inbox()
    if inbox:
        sections.append(f"*📬 Inbox*\n{inbox}")

    reminders = _get_reminders()
    if reminders:
        sections.append(f"*⏰ Reminders*\n{reminders}")

    jobs = _get_jobs()
    if jobs:
        sections.append(f"*🎯 Job matches*\n{jobs}")

    news = _get_news()
    if news:
        sections.append(f"*📰 News*\n{news}")

    if len(sections) == 1:
        sections.append("Nothing urgent today. Clear runway.")

    message = "\n\n".join(sections)
    _send_telegram(message)
    print(f"Brief sent at {now:%H:%M}")
