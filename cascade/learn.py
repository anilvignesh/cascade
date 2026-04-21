"""
Synthesis loop — reads memory, infers user patterns, updates context.md.

Run: cascade learn
Or schedule as a nightly cron.

Gemini reads raw memory and writes a structured [LEARNED] block into
context.md. The rest of context.md (user-written ROM) is preserved.
"""

from datetime import datetime
from pathlib import Path

import yaml

from .llm    import call_role
from .memory import _paths, mempalace_search

_CONFIG_PATH = Path(__file__).parent.parent / "config.yml"

LEARN_PROMPT = """\
You are analyzing a user's interaction history with an AI assistant called Cascade.
Your job is to extract stable, reusable patterns about this user.

--- INTERACTION HISTORY ---
{history}
--- END ---

Write a concise structured profile block. Focus on:
- Communication style preferences (brief? detailed? technical?)
- Frequent topics and domains they ask about
- Which tasks they route to Claude vs Gemini (coding vs research)
- Apparent goals, projects, or ongoing work
- Any corrections they made (what they pushed back on)

Format your response EXACTLY like this — no extra text before or after:

[LEARNED] {date}
- <insight 1>
- <insight 2>
- <insight 3>
...
[/LEARNED]

Be specific and factual. Only write what is clearly evidenced in the history.
Do not invent or speculate."""


def _read_memory() -> str:
    mem_path, _ = _paths()
    return mem_path.read_text().strip()


def _read_mempalace() -> str:
    return mempalace_search("cascade user behavior preferences topics")


def _strip_learned_block(text: str) -> str:
    """Remove any existing [LEARNED]...[/LEARNED] block from context.md."""
    import re
    return re.sub(
        r'\[LEARNED\].*?\[/LEARNED\]', '', text, flags=re.DOTALL
    ).strip()


def run(verbose: bool = True) -> str:
    mem_path, ctx_path = _paths()

    # Gather history from both layers
    hdd = _read_memory()
    ram = _read_mempalace()

    history_parts = []
    if hdd:
        history_parts.append(f"=== Past conversations (memory.md) ===\n{hdd[:6000]}")
    if ram:
        history_parts.append(f"=== Semantic memory (MemPalace) ===\n{ram[:2000]}")

    if not history_parts:
        msg = "No memory found — use Cascade more before running learn."
        if verbose: print(msg)
        return msg

    history = "\n\n".join(history_parts)
    prompt  = LEARN_PROMPT.format(history=history, date=datetime.now().strftime("%Y-%m-%d"))

    if verbose:
        print("◆ CASCADE LEARN — analysing memory with Gemini...")

    learned = call_role("interpreter", prompt)

    # Validate we got the expected format
    if "[LEARNED]" not in learned or "[/LEARNED]" not in learned:
        msg = f"Unexpected response from Gemini:\n{learned}"
        if verbose: print(msg)
        return msg

    # Preserve user-written ROM, replace only the [LEARNED] block
    existing = ctx_path.read_text()
    clean    = _strip_learned_block(existing)
    updated  = f"{clean}\n\n{learned}".strip() if clean else learned
    ctx_path.write_text(updated + "\n")

    if verbose:
        print(f"\n✓ context.md updated\n\n{learned}\n")

    return learned
