"""
/match — match a resume against current job listings.
Usage: /match (then upload resume, or paste resume text after the command)
"""

import sys, json
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".jarvis"))

DESCRIPTION = "Match resume against current job listings"


def run(query: str = "", context: str = "") -> str:
    try:
        from agents.job_hunter import fetch
        data = fetch()
        jobs = data.get("jobs", [])
        if not jobs:
            return "No job listings cached. Try /jobs refresh first."
    except Exception as e:
        return f"Could not load jobs: {e}"

    if not query and not context:
        return "Paste your resume text after /match, or upload a PDF/DOCX file."

    resume = context or query
    jobs_text = "\n".join(
        f"- {j.get('title','')} at {j.get('company','')} ({j.get('location','')}): {j.get('url','')}"
        for j in jobs
    )

    try:
        sys.path.insert(0, str(Path.home() / "cascade"))
        from cascade.llm import call_claude
        prompt = (
            f"Resume:\n{resume[:3000]}\n\n"
            f"Job listings:\n{jobs_text}\n\n"
            f"Rank these jobs by fit for this resume. For the top 3, explain specifically why "
            f"the candidate's background matches. Be direct and honest about gaps too."
        )
        return call_claude(prompt)
    except Exception as e:
        return f"Matching error: {e}"
