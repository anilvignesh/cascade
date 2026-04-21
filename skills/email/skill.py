"""
/email — smart email agent. Reads full thread context before drafting.

/email inbox                        — summarise last 5 emails (Gemini)
/email read <subject>               — read a specific email
/email reply <subject>: <intent>    — read full thread, draft reply (Claude)
/email send <to> | <subject> | <body>
/email search <query>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "cascade"))

DESCRIPTION = "Smart email agent — reads thread context before drafting replies"

PROFILE = """You are drafting on behalf of Anil Vignesh, Senior PM in cross-border payments.
His voice: direct, professional, concise. No filler phrases like 'I hope this finds you well'.
He works at EximPe (RBI PA-CB licensed payment aggregator) in Bengaluru.
Sign off as: Anil"""

GMAIL_TOOLS = ",".join([
    "mcp__claude_ai_Gmail__search_threads",
    "mcp__claude_ai_Gmail__get_thread",
    "mcp__claude_ai_Gmail__list_labels",
    "mcp__claude_ai_Gmail__create_draft",
    "mcp__claude_ai_Gmail__label_thread",
])


def _run_claude(prompt: str, tools: str = GMAIL_TOOLS) -> str:
    import subprocess
    claude_bin = str(Path.home() / ".local" / "bin" / "claude")
    result = subprocess.run(
        [claude_bin, "-p", prompt,
         "--allowedTools", tools,
         "--dangerously-skip-permissions"],
        capture_output=True, text=True, timeout=120
    )
    return result.stdout.strip() or result.stderr.strip()


def _run_gemini(prompt: str) -> str:
    from cascade.llm import call_gemini
    return call_gemini(prompt)


def _inbox(limit: int = 5) -> str:
    # Fetch raw from Claude+Gmail MCP, then Gemini summarises
    raw = _run_claude(
        f"Use Gmail MCP to fetch the last {limit} email threads. "
        f"For each return: sender name, subject, date, and the full first message body (max 300 chars). "
        f"Format as plain text, one thread per section."
    )
    if not raw or "error" in raw.lower()[:30]:
        return raw or "Could not fetch inbox."

    summary = _run_gemini(
        f"Summarise these emails for a Senior PM. Be concise — one line per email.\n"
        f"Flag anything urgent or from recruiters/target companies "
        f"(Checkout.com, Airwallex, Nium, Wise, Tabby, Tamara, dLocal, Xflow).\n\n{raw}"
    )
    return summary


def _read(subject_or_id: str) -> str:
    return _run_claude(
        f"Use Gmail MCP to find and read the email thread about: '{subject_or_id}'. "
        f"Return sender, subject, date, and full body."
    )


def _reply(subject_or_id: str, intent: str) -> str:
    # Step 1: read the full thread
    thread = _run_claude(
        f"Use Gmail MCP to find the email thread about: '{subject_or_id}'. "
        f"Return the full conversation — all messages, senders, and dates in order."
    )
    if not thread or "error" in thread.lower()[:30]:
        return f"Could not find thread: {subject_or_id}"

    # Step 2: Claude drafts the reply with full context
    draft = _run_claude(
        f"{PROFILE}\n\n"
        f"Full email thread:\n{thread}\n\n"
        f"Draft intent: {intent}\n\n"
        f"Write the reply. Return only the email body — no subject line, no metadata. "
        f"Ready to send as-is.",
        tools="",  # no MCP tools needed for drafting
    )
    return f"DRAFT REPLY:\n\n{draft}"


def _send(to: str, subject: str, body: str) -> str:
    return _run_claude(
        f"Use Gmail MCP to create a draft email.\n"
        f"To: {to}\nSubject: {subject}\nBody:\n{body}\n\n"
        f"Create the draft and confirm."
    )


def _search(query: str) -> str:
    return _run_claude(
        f"Use Gmail MCP to search email threads for: '{query}'. "
        f"Return top 5 results: sender, subject, date, one-line summary."
    )


def run(query: str = "", context: str = "") -> str:
    if not query:
        return (
            "Usage:\n"
            "  /email inbox\n"
            "  /email read <subject>\n"
            "  /email reply <subject>: <what you want to say>\n"
            "  /email send <to> | <subject> | <body>\n"
            "  /email search <query>"
        )

    q = query.strip()

    if q == "inbox":
        return _inbox()

    if q.startswith("read "):
        return _read(q[5:].strip())

    if q.startswith("reply "):
        rest = q[6:].strip()
        if ":" in rest:
            subject, intent = rest.split(":", 1)
            return _reply(subject.strip(), intent.strip())
        return "Usage: /email reply <subject>: <what you want to say>"

    if q.startswith("send "):
        parts = q[5:].split("|")
        if len(parts) == 3:
            return _send(parts[0].strip(), parts[1].strip(), parts[2].strip())
        return "Usage: /email send <to> | <subject> | <body>"

    if q.startswith("search "):
        return _search(q[7:].strip())

    return _search(q)
