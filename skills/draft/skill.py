"""
/draft — structured document drafter. Claude writes, Gemini researches if needed.

Usage:
  /draft prd <feature or product name>      — Product Requirements Document
  /draft cover <company> [role]             — Cover letter in Anil's voice
  /draft proposal <topic>                   — Business or technical proposal
  /draft email <intent>                     — Cold outreach or professional email
  /draft <anything>                         — Free-form, format inferred
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "cascade"))

DESCRIPTION = "Document drafter — PRDs, cover letters, proposals, outreach emails"

PROFILE = """Anil Vignesh — Senior PM, 8 years (Engineering → Data Science → Product).
Current: EximPe, Bengaluru — RBI PA-CB licensed payment aggregator.
Core expertise: Cross-border payments, Pay-In, FX Settlement, PSP integrations, KYC/AML, PA-CB, PCI DSS.
Job search: Senior PM / Head of Product — Dubai > UAE > Middle East > Remote.
Target companies: Checkout.com, Airwallex, Tabby, Tamara, Nium, Wise, OpenFX, Xflow, dLocal.
Writing voice: Direct, professional, concise. No filler. No corporate speak."""


def _web_search(query: str) -> str:
    try:
        from cascade.browser import search
        return search(query)[:2000]
    except Exception as e:
        return f"(web search unavailable: {e})"


def _mem_context(query: str) -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["mempalace", "search", query, "--limit", "3"],
            capture_output=True, text=True, timeout=8
        )
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and not l.startswith(("Search", "===", "---", "["))]
        return "\n".join(lines)[:800]
    except Exception:
        return ""


# ── Mode handlers ──────────────────────────────────────────────────────────────

def _draft_prd(feature: str, context: str) -> str:
    from cascade.llm import call_claude

    mem = _mem_context(f"product {feature}")

    prompt = f"""You are writing a PRD for Anil Vignesh, Senior PM at EximPe (cross-border payments).

Profile:
{PROFILE}

Feature / Product: {feature}
{f'Additional context: {context}' if context else ''}

Memory context:
{mem if mem else '(none)'}

Write a complete Product Requirements Document with these sections:

## Overview
- One-paragraph summary of what this is and why it matters

## Problem Statement
- What user/business problem does this solve?
- Who is affected and how severely?

## Goals & Success Metrics
- 2-3 measurable goals
- KPIs to track success

## User Stories
- 3-5 core user stories in standard format (As a... I want... So that...)

## Functional Requirements
- Numbered list of what the system must do
- Mark priority: P0 (must-have), P1 (should-have), P2 (nice-to-have)

## Non-Functional Requirements
- Performance, security, compliance, scalability constraints

## Out of Scope
- What this version explicitly does NOT cover

## Open Questions
- Decisions that still need to be made before building

## Dependencies & Risks
- What needs to be in place, what could go wrong

Be specific. Use real numbers where possible. Write as if this goes to engineering tomorrow."""

    return call_claude(prompt)


def _draft_cover(company: str, role: str, context: str) -> str:
    from cascade.llm import call_gemini, call_claude

    web = _web_search(f"{company} payments fintech product team 2026")
    mem = _mem_context(company)

    research_prompt = f"""Research {company} briefly for a job application.
Web data: {web}
Memory: {mem if mem else '(none)'}
Return: what they do, 2-3 things that make them interesting, what kind of PM they likely want."""

    company_brief = call_gemini(research_prompt)

    prompt = f"""Write a cover letter for Anil Vignesh applying to {company}.

Candidate profile:
{PROFILE}

Role: {role if role else 'Senior PM / Head of Product'}
{f'Additional context: {context}' if context else ''}

Company brief:
{company_brief}

Write the cover letter:
- 3 tight paragraphs, no header/address block needed
- Para 1: Why this company, why now — reference something specific about them
- Para 2: Two concrete things from his experience that map directly to what they need
  (lead with RBI PA-CB experience and cross-border infra knowledge)
- Para 3: One forward-looking sentence + close

Voice: Direct, confident, no filler phrases. No "I am pleased to apply" or "I hope to hear from you".
Sign off: Anil Vignesh

Write only the letter body. Nothing else."""

    return call_claude(prompt)


def _draft_proposal(topic: str, context: str) -> str:
    from cascade.llm import call_claude

    web = _web_search(topic)
    mem = _mem_context(topic)

    prompt = f"""Write a business/technical proposal for Anil Vignesh.

Profile:
{PROFILE}

Topic: {topic}
{f'Additional context: {context}' if context else ''}

Web context:
{web}

Memory:
{mem if mem else '(none)'}

Write a structured proposal:

## Executive Summary
- What is being proposed and what outcome it achieves (2-3 sentences)

## Background & Context
- Why this matters now, what triggered the need

## Proposed Solution
- What specifically is being proposed
- Key components or phases

## Business Case
- Expected benefits (quantified where possible)
- Cost or effort estimate

## Implementation Plan
- High-level timeline with key milestones

## Risks & Mitigations
- Top 2-3 risks with mitigations

## Ask / Next Steps
- What decision or action is needed from the reader

Keep it tight. This should be readable in under 5 minutes."""

    return call_claude(prompt)


def _draft_email(intent: str, context: str) -> str:
    from cascade.llm import call_claude

    mem = _mem_context(intent)

    prompt = f"""Draft a professional email for Anil Vignesh.

Profile:
{PROFILE}

Email intent: {intent}
{f'Additional context: {context}' if context else ''}

Memory context:
{mem if mem else '(none)'}

Write the email:
- Subject line (clearly labelled)
- Body: direct, professional, no filler
- If cold outreach: one specific hook, clear ask, short
- If follow-up: reference the previous interaction, move forward
- Sign off: Anil

Return subject + body only."""

    return call_claude(prompt)


def _draft_freeform(task: str, context: str) -> str:
    from cascade.llm import call_claude

    mem = _mem_context(task)

    prompt = f"""Draft a document for Anil Vignesh.

Profile:
{PROFILE}

Task: {task}
{f'Additional context: {context}' if context else ''}

Memory:
{mem if mem else '(none)'}

Infer the appropriate document format and write it.
Be specific, professional, and use Anil's direct voice.
Include a clear structure with headers."""

    return call_claude(prompt)


# ── Mode detection ─────────────────────────────────────────────────────────────

def _detect_mode(query: str) -> tuple[str, str, str]:
    """Returns (mode, subject, extra_context)."""
    q = query.strip()

    for mode in ("prd", "cover", "proposal", "email"):
        if q.lower().startswith(mode + " ") or q.lower().startswith(mode + ","):
            rest  = q[len(mode):].strip().lstrip(",").strip()
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
            "  /draft prd <feature>                    — Product Requirements Document\n"
            "  /draft cover <company> [role]           — Cover letter in your voice\n"
            "  /draft proposal <topic>                 — Business or technical proposal\n"
            "  /draft email <intent>                   — Cold outreach or professional email\n"
            "  /draft <anything>                       — Free-form document"
        )

    mode, subject, extra = _detect_mode(query)
    full_context = " | ".join(filter(None, [extra, context]))

    print(f"  drafting {mode}: {subject}…", flush=True)

    if mode == "prd":
        return _draft_prd(subject, full_context)
    elif mode == "cover":
        return _draft_cover(subject, extra, full_context)
    elif mode == "proposal":
        return _draft_proposal(subject, full_context)
    elif mode == "email":
        return _draft_email(subject, full_context)
    else:
        return _draft_freeform(subject, full_context)
