"""
/jobs — smart job briefing via Gemini.
Fetches from cache, Gemini analyses fit and tells you exactly what to do.

/jobs            — analyse high-fit jobs
/jobs all        — include medium-fit jobs too
/jobs refresh    — force fresh fetch then analyse
/jobs raw        — raw list, no analysis
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".jarvis"))
sys.path.insert(0, str(Path.home() / "cascade"))

DESCRIPTION = "Job fit analysis — what to apply for and what to say"

PROFILE = """Anil Vignesh — Senior PM, 8 years experience (Software Engineering → Data Science → Product).
Current: EximPe (RBI PA-CB licensed payment aggregator) — built Pay-In, Virtual Accounts, FX settlement flows.
Core expertise: Cross-border payments, PSP integrations, KYC/AML, RBI PA-CB compliance, PCI DSS, FX.
Target roles: Senior PM, Head of Product, PM2 — in payments, fintech, or AI.
Locations: Dubai (top priority) > UAE > Middle East > Southeast Asia > Remote > India.
Target companies: Checkout.com, Airwallex, Tabby, Tamara, Nium, Wise, OpenFX, Xflow, dLocal.
Strengths to highlight: RBI PA-CB licence experience (rare), full-stack payment infra knowledge,
  technical background (built systems before becoming PM), cross-border FX expertise."""


def _fetch_jobs(force: bool = False) -> tuple[list, str]:
    from agents.job_hunter import fetch
    data = fetch(force=force)
    return data.get("jobs", []), data.get("updated", "")


def _format_raw(jobs: list, updated: str) -> str:
    if not jobs:
        return "No jobs cached. Try: /jobs refresh"
    lines = [f"Jobs · {updated}\n"]
    for j in jobs[:10]:
        dot = "●" if j.get("fit") == "high" else "○"
        lines.append(f"{dot} {j.get('title','')} — {j.get('company','')} ({j.get('location','')})")
        if j.get("url"):
            lines.append(f"  {j['url'][:70]}")
    return "\n".join(lines)


def _analyse_with_gemini(jobs: list, updated: str, include_all: bool = False) -> str:
    from cascade.llm import call_gemini

    target_jobs = [j for j in jobs if j.get("fit") == "high"] if not include_all else jobs
    if not target_jobs:
        target_jobs = jobs[:8]

    if not target_jobs:
        return "No jobs cached. Try: /jobs refresh"

    jobs_text = "\n\n".join(
        f"- {j.get('title','')} at {j.get('company','')} ({j.get('location','')})\n"
        f"  Fit: {j.get('fit','?')} | {j.get('reason','')}\n"
        f"  URL: {j.get('url','')}"
        for j in target_jobs[:8]
    )

    prompt = f"""You are a career advisor for a Senior PM in cross-border payments.

Candidate profile:
{PROFILE}

Job listings (fetched {updated}):
{jobs_text}

For each job, give:
1. **Role @ Company** — one line on why this is a good match (or flag if it's not)
2. What to highlight in the application (specific experience that fits)
3. One gap or risk to address

Then end with: which ONE job should they apply to first and why.

Be specific and direct. No generic advice."""

    return call_gemini(prompt)


def run(query: str = "", context: str = "") -> str:
    try:
        force       = "refresh" in query.lower()
        raw_mode    = "raw" in query.lower()
        include_all = "all" in query.lower()

        jobs, updated = _fetch_jobs(force=force)

        if not jobs:
            return "No jobs cached. Try: /jobs refresh"

        if raw_mode:
            return _format_raw(jobs, updated)

        return _analyse_with_gemini(jobs, updated, include_all=include_all)

    except Exception as e:
        return f"jobs skill error: {e}"
