"""
/plan — Chief of Staff skill. Prepares structured briefings before you act.

Usage:
  /plan trip <destination> [dates]      — visa, areas, itinerary, budget
  /plan research <company or topic>     — deep brief with fresh web data
  /plan interview <company> [role]      — prep pack: fit, questions, talking points
  /plan meeting <person or topic>       — agenda, context, what to push for
  /plan <anything>                      — free-form, structure inferred
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "cascade"))
sys.path.insert(0, str(Path.home() / ".jarvis"))

DESCRIPTION = "Chief of staff — trip plans, research briefs, interview prep, meeting agendas"

PROFILE = """Anil Vignesh — Senior PM, 8 years (Engineering → Data Science → Product).
Current: EximPe, Bengaluru — RBI PA-CB licensed payment aggregator.
Expertise: Cross-border payments, Pay-In, FX Settlement, PSP integrations, KYC/AML, PA-CB, PCI DSS.
Job search: Senior PM / Head of Product — Dubai > UAE > Middle East > Remote.
Target companies: Checkout.com, Airwallex, Tabby, Tamara, Nium, Wise, OpenFX, Xflow, dLocal.
Partner: Fio. Based in Bengaluru. Indian passport holder."""


# ── Web research helpers ───────────────────────────────────────────────────────

def _web_search(query: str, num: int = 3) -> str:
    """Run DuckDuckGo search, return top results as text."""
    try:
        from cascade.browser import search
        return search(query)[:3000]
    except Exception as e:
        return f"(web search unavailable: {e})"


def _web_fetch(url: str) -> str:
    try:
        from cascade.browser import browse
        return browse(url)[:3000]
    except Exception as e:
        return f"(fetch failed: {e})"


# ── MemPalace context ──────────────────────────────────────────────────────────

def _mem_context(query: str) -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["mempalace", "search", query, "--limit", "3"],
            capture_output=True, text=True, timeout=8
        )
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and not l.startswith(("Search", "===", "---", "["))]
        return "\n".join(lines)[:1000]
    except Exception:
        return ""


# ── Mode handlers ──────────────────────────────────────────────────────────────

def _plan_trip(destination: str, context: str) -> str:
    from cascade.llm import call_gemini

    web = _web_search(f"travel {destination} visa requirements Indians 2026")
    web += "\n\n" + _web_search(f"best areas to stay {destination} for professionals")
    mem = _mem_context(f"trip {destination}")

    prompt = f"""You are preparing a trip brief for Anil Vignesh.

Profile:
{PROFILE}

Destination: {destination}
{f'Additional context: {context}' if context else ''}

Fresh web research:
{web}

Prior knowledge from memory:
{mem if mem else '(none)'}

Write a structured trip brief with these sections:
## Visa & Entry
- Requirements for Indian passport holders, processing time, cost

## Where to Stay
- 2-3 recommended areas with reason (budget, vibe, commute)

## 3-Day Itinerary
- Day-by-day plan (professional angle if job hunting)

## Budget Estimate
- Flights, accommodation, daily spend (INR and local currency)

## Practical Tips
- SIM card, transport, useful apps, cultural notes

## If Job Hunting There
- Co-working spaces, networking events, neighbourhoods where fintech companies cluster

Be specific. Use actual names and numbers where possible."""

    return call_gemini(prompt)


def _plan_research(topic: str, context: str) -> str:
    from cascade.llm import call_gemini

    # Determine if it's a company or a broader topic
    web1 = _web_search(f"{topic} company overview product 2026")
    web2 = _web_search(f"{topic} news funding team 2026")
    mem  = _mem_context(topic)

    prompt = f"""You are preparing a research brief for Anil Vignesh, Senior PM in cross-border payments.

Profile:
{PROFILE}

Research subject: {topic}
{f'Focus: {context}' if context else ''}

Web research:
{web1}

{web2}

Prior knowledge from memory:
{mem if mem else '(none)'}

Write a structured research brief:
## Overview
- What it is, who built it, when founded, size

## Product & Business Model
- Core product, how they make money, key differentiators

## Recent News
- Funding, partnerships, product launches, leadership changes (last 6 months)

## Key People
- Founders, CEO, CPO — background and style

## Relevance to Anil
- Why this matters given his background in cross-border payments
- Is this a potential employer, competitor, partner, or market trend?

## Open Questions
- Things worth digging into further

Be specific. Flag anything that's uncertain or needs verification."""

    return call_gemini(prompt)


def _plan_interview(company: str, role: str, context: str) -> str:
    from cascade.llm import call_gemini

    web1 = _web_search(f"{company} product payments fintech overview")
    web2 = _web_search(f"{company} {role} interview process culture 2026")
    mem  = _mem_context(company)

    prompt = f"""You are preparing an interview prep pack for Anil Vignesh.

His profile:
{PROFILE}

Company: {company}
Role: {role if role else 'Senior PM / Head of Product'}
{f'Additional context: {context}' if context else ''}

Company research:
{web1}

Interview intel:
{web2}

Prior knowledge from memory:
{mem if mem else '(none)'}

Write a structured interview prep pack:
## Company in 60 Seconds
- What they do, key numbers, positioning

## Why Anil Fits
- Specific overlaps between his background and what this company needs
- Lead with RBI PA-CB experience, cross-border payments infra, technical background

## Gaps to Address
- Where his background doesn't match — and how to frame it positively

## Likely Interview Questions
- 5 questions they'll probably ask for this role
- For each: suggested angle based on his experience

## Talking Points to Prepare
- 3 stories from his EximPe experience that translate well here
- One insight about their product/market that shows he's done his homework

## Questions to Ask Them
- 3 sharp questions that signal strategic thinking

## Red Flags to Watch
- Anything from research that suggests culture fit issues or role mismatch

Be direct. This is a prep tool, not a motivational speech."""

    return call_gemini(prompt)


def _plan_meeting(person_or_topic: str, context: str) -> str:
    from cascade.llm import call_gemini

    mem = _mem_context(person_or_topic)
    web = _web_search(f"{person_or_topic} 2026") if not mem else ""

    prompt = f"""You are preparing a pre-meeting brief for Anil Vignesh.

His profile:
{PROFILE}

Meeting subject: {person_or_topic}
{f'Context: {context}' if context else ''}

Memory context:
{mem if mem else '(none)'}

{f'Web context:{chr(10)}{web}' if web else ''}

Write a structured meeting brief:
## Who / What
- Quick background on the person or topic

## Why This Meeting Matters
- Stakes, opportunity, or risk

## Suggested Agenda
- 3-4 agenda items in priority order (time box each)

## What to Push For
- The specific outcome Anil should aim to walk out with

## What to Watch Out For
- Things that might derail the meeting or need careful handling

## Talking Points
- 2-3 things to lead with

## What to Bring / Prepare
- Data, docs, or decisions needed before walking in

Keep it tight — this is a 2-minute read before a meeting."""

    return call_gemini(prompt)


def _plan_freeform(task: str, context: str) -> str:
    from cascade.llm import call_gemini

    web = _web_search(task)
    mem = _mem_context(task)

    prompt = f"""You are Anil Vignesh's chief of staff. He needs help planning something.

His profile:
{PROFILE}

Task: {task}
{f'Additional context: {context}' if context else ''}

Web research:
{web}

Memory context:
{mem if mem else '(none)'}

Infer what kind of plan is needed and structure your output accordingly.
Always include:
- A clear summary of what needs to happen
- Concrete next steps in priority order
- Any risks or blockers to flag
- A recommended first action

Be specific and actionable. No filler."""

    return call_gemini(prompt)


# ── Mode detection ─────────────────────────────────────────────────────────────

def _detect_mode(query: str) -> tuple[str, str, str]:
    """Returns (mode, subject, extra_context)."""
    q = query.strip()

    for mode in ("trip", "research", "interview", "meeting"):
        if q.lower().startswith(mode + " ") or q.lower().startswith(mode + ","):
            rest = q[len(mode):].strip().lstrip(",").strip()
            # For interview: "interview Airwallex PM role" → subject=Airwallex, context=PM role
            parts = rest.split(" ", 2)
            subject = parts[0] if parts else rest
            extra   = " ".join(parts[1:]) if len(parts) > 1 else ""
            return mode, subject, extra

    return "freeform", q, ""


# ── Entry point ────────────────────────────────────────────────────────────────

def run(query: str = "", context: str = "") -> str:
    if not query:
        return (
            "Usage:\n"
            "  /plan trip <destination> [dates/purpose]\n"
            "  /plan research <company or topic>\n"
            "  /plan interview <company> [role]\n"
            "  /plan meeting <person or topic>\n"
            "  /plan <anything>"
        )

    mode, subject, extra = _detect_mode(query)

    # Merge skill context (from session/memory) with detected extra
    full_context = " | ".join(filter(None, [extra, context]))

    print(f"  preparing {mode} brief for: {subject}…", flush=True)

    if mode == "trip":
        return _plan_trip(subject, full_context)
    elif mode == "research":
        return _plan_research(subject, full_context)
    elif mode == "interview":
        return _plan_interview(subject, extra, full_context)
    elif mode == "meeting":
        return _plan_meeting(subject, full_context)
    else:
        return _plan_freeform(subject, full_context)
