"""
Cascade Watcher — 24/7 background agent.
Monitors jobs and news, sends Telegram alerts on new high-fit matches.

Run via cron:
  */30 * * * * /home/jarvis/.local/bin/cascade watch >> ~/.cascade-watcher.log 2>&1
"""

import json, os, time, subprocess, hashlib
from datetime import datetime
from pathlib import Path

SEEN_FILE  = Path.home() / ".jarvis" / "cache" / "watcher_seen.json"
ENV_FILE   = Path.home() / ".cascade.env"

SCORE_THRESHOLD = "high"  # only alert on high-fit jobs


def _load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _load_seen() -> set:
    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        return set()


def _save_seen(seen: set):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(list(seen)))


def _job_id(job: dict) -> str:
    key = f"{job.get('title','')}{job.get('company','')}{job.get('url','')}"
    return hashlib.md5(key.encode()).hexdigest()


def _news_id(item: dict) -> str:
    key = f"{item.get('title','')}{item.get('url','')}"
    return hashlib.md5(key.encode()).hexdigest()


def _send_telegram(message: str):
    _load_env()
    token   = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("  Telegram not configured, skipping notification")
        return
    try:
        import urllib.request, urllib.parse
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": "Markdown",
        }).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
        print(f"  Telegram sent: {message[:60]}...")
    except Exception as e:
        print(f"  Telegram error: {e}")


def check_jobs(seen: set) -> tuple[list[str], set]:
    import sys
    sys.path.insert(0, str(Path.home() / ".jarvis"))

    alerts = []
    try:
        from agents.job_hunter import fetch
        data = fetch(force=True)
        jobs = data.get("jobs", [])

        for job in jobs:
            if job.get("fit") != SCORE_THRESHOLD:
                continue
            jid = _job_id(job)
            if jid in seen:
                continue

            seen.add(jid)
            title   = job.get("title", "")
            company = job.get("company", "")
            loc     = job.get("location", "")
            url     = job.get("url", "")
            reason  = job.get("reason", "")

            msg = (
                f"🎯 *New high-fit job*\n\n"
                f"*{title}*\n"
                f"{company} · {loc}\n"
                f"{reason}\n\n"
                f"[Apply]({url})"
            )
            alerts.append(msg)
            print(f"  New job: {title} @ {company}")

    except Exception as e:
        print(f"  Job check error: {e}")

    return alerts, seen


def check_news(seen: set) -> tuple[list[str], set]:
    import sys
    sys.path.insert(0, str(Path.home() / ".jarvis"))

    alerts = []
    try:
        from agents.fintech_monitor import fetch
        data = fetch(force=True)
        cats = data.get("categories", {})

        for cat, items in cats.items():
            for item in items:
                nid = _news_id(item)
                if nid in seen:
                    continue
                seen.add(nid)

                title   = item.get("title", "")
                summary = item.get("summary", "")
                url     = item.get("url", "")

                label = {
                    "fintech":    "Fintech",
                    "stablecoin": "Stablecoins",
                    "rbi":        "RBI",
                    "llm":        "AI/LLM",
                    "nium":       "Target Co",
                }.get(cat, cat.upper())

                msg = (
                    f"📰 *{label}*\n\n"
                    f"*{title}*\n"
                    f"{summary[:200]}"
                    + (f"\n[Read]({url})" if url else "")
                )
                alerts.append(msg)

    except Exception as e:
        print(f"  News check error: {e}")

    return alerts, seen


def run():
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M}] Cascade Watcher running...")
    seen = _load_seen()

    # Check jobs
    print("Checking jobs...")
    job_alerts, seen = check_jobs(seen)
    for msg in job_alerts:
        _send_telegram(msg)
        time.sleep(1)

    # Check news
    print("Checking news...")
    news_alerts, seen = check_news(seen)
    # Only send top 3 news items per run to avoid spam
    for msg in news_alerts[:3]:
        _send_telegram(msg)
        time.sleep(1)

    _save_seen(seen)

    total = len(job_alerts) + len(news_alerts)
    print(f"Done. {len(job_alerts)} job alerts, {len(news_alerts)} news alerts sent.")
    return total
