"""
Email agent — read, draft, send via Gmail MCP through Claude.
Requires Gmail MCP authenticated in Claude Code first:
  1. Run `claude` in terminal
  2. Type /mcp → select "claude.ai Gmail" → complete OAuth
  3. Done — this module works from that point on
"""

import subprocess
from pathlib import Path

CLAUDE_BIN = str(Path.home() / ".local" / "bin" / "claude")
GMAIL_TOOLS = (
    "mcp__claude_ai_Gmail__authenticate,"
    "mcp__claude_ai_Gmail__complete_authentication"
)


def _run(prompt: str, tools: str = GMAIL_TOOLS) -> str:
    result = subprocess.run(
        [CLAUDE_BIN, "-p", prompt,
         "--allowedTools", tools,
         "--dangerously-skip-permissions"],
        capture_output=True, text=True, timeout=120
    )
    return result.stdout.strip() or result.stderr.strip()


def read_inbox(limit: int = 5) -> str:
    return _run(
        f"Use Gmail MCP to fetch my last {limit} emails. "
        f"For each: sender, subject, date, 1-sentence summary. "
        f"Format as a clean list. No markdown headers."
    )


def read_email(subject_or_id: str) -> str:
    return _run(
        f"Use Gmail MCP to find and read the email about: '{subject_or_id}'. "
        f"Return full content."
    )


def draft_reply(subject_or_id: str, instructions: str) -> str:
    return _run(
        f"Use Gmail MCP to find the email about: '{subject_or_id}'. "
        f"Draft a reply based on these instructions: {instructions}. "
        f"Return only the draft text, ready to send."
    )


def send_email(to: str, subject: str, body: str) -> str:
    return _run(
        f"Use Gmail MCP to send an email.\n"
        f"To: {to}\nSubject: {subject}\nBody:\n{body}\n\n"
        f"Confirm when sent."
    )


def search_emails(query: str) -> str:
    return _run(
        f"Use Gmail MCP to search emails for: '{query}'. "
        f"Return top 5 results with sender, subject, date, summary."
    )
