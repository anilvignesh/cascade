"""
/news — curated fintech/payments briefing via Gemini.
Fetches from cache, then Gemini contextualises for Anil's profile.

/news            — today's briefing
/news refresh    — force fresh fetch before briefing
/news raw        — raw headlines, no analysis
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".jarvis"))
sys.path.insert(0, str(Path.home() / "cascade"))

DESCRIPTION = "Curated fintech & payments briefing with relevance analysis"

PROFILE = """Anil Vignesh — Senior PM, cross-border payments & fintech.
- Currently at EximPe (RBI PA-CB licensed payment aggregator), Bengaluru
- Expertise: Pay-In, Virtual Accounts, FX Settlement, PSP integrations, KYC/AML, RBI PA-CB, PCI DSS
- Actively job hunting: targeting Senior PM / Head of Product in Dubai > UAE > Middle East
- Target companies: Checkout.com, Airwallex, Tabby, Tamara, Nium, Wise, OpenFX, Xflow, dLocal
- Interests: Stablecoins, cross-border payment infra, AI/LLMs in fintech"""

LABELS = {
    "fintech":    "Fintech & Payments",
    "stablecoin": "Stablecoins",
    "rbi":        "RBI & Regulation",
    "llm":        "AI / LLM",
    "nium":       "Target Companies",
}


def _fetch_raw(force: bool = False) -> tuple[dict, str]:
    from agents.fintech_monitor import fetch
    data = fetch(force=force)
    return data.get("categories", {}), data.get("updated", "")


def _format_raw(cats: dict, updated: str) -> str:
    lines = [f"News · {updated}\n"]
    for cat, items in cats.items():
        if not items:
            continue
        lines.append(LABELS.get(cat, cat.upper()))
        for item in items[:3]:
            lines.append(f"  · {item.get('title', '')}")
            if item.get("summary"):
                lines.append(f"    {item['summary'][:120]}")
    return "\n".join(lines)


def _analyse_with_gemini(cats: dict, updated: str) -> str:
    from cascade.llm import call_gemini

    # Build a compact news digest for Gemini to work with
    sections = []
    for cat, items in cats.items():
        if not items:
            continue
        label = LABELS.get(cat, cat.upper())
        items_text = "\n".join(
            f"  - {i.get('title', '')} | {i.get('summary', '')[:150]}"
            for i in items[:4]
        )
        sections.append(f"{label}:\n{items_text}")

    if not sections:
        return "No news available. Try: /news refresh"

    news_text = "\n\n".join(sections)

    prompt = f"""You are briefing a Senior PM in cross-border payments on today's industry news.

User profile:
{PROFILE}

Today's news ({updated}):
{news_text}

Write a concise briefing (under 300 words):
1. Pick the 3-4 most relevant items for this person
2. For each: one line on what happened, one line on why it matters to them specifically
3. End with one "watch out" — a trend or risk they should be tracking

Be direct. No filler. Talk to them like a smart colleague who read the news for them."""

    return call_gemini(prompt)


def run(query: str = "", context: str = "") -> str:
    try:
        force   = "refresh" in query.lower()
        raw_mode = "raw" in query.lower()

        cats, updated = _fetch_raw(force=force)

        if not any(cats.values()):
            return "No news cached. Try: /news refresh"

        if raw_mode:
            return _format_raw(cats, updated)

        return _analyse_with_gemini(cats, updated)

    except Exception as e:
        return f"news skill error: {e}"
