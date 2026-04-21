"""
LLM backends — three-tier architecture.
- Local:  Qwen3 via Ollama (streaming + batch) — free, private
- Gemini: Gemini CLI — research, analysis, conversation, long context
- Claude: Claude Code CLI — complex coding, architecture, implementation
"""

import json, subprocess, urllib.request
from pathlib import Path
from typing import Iterator

OLLAMA_URL  = "http://localhost:11434/api/chat"
LOCAL_MODEL = "qwen3:8b"
CLAUDE_BIN  = str(Path.home() / ".local" / "bin" / "claude")
GEMINI_BIN  = str(Path.home() / ".local" / "bin" / "gemini")

ENGLISH_RULE = "IMPORTANT: Always respond in English only."


def _build_messages(messages: list[dict]) -> list[dict]:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    return [
        {"role": "system", "content": f"{system}\n\n{ENGLISH_RULE}".strip()},
        *[m for m in messages if m["role"] != "system"]
    ]


def call_local(messages: list[dict], max_tokens: int = 2048, timeout: int = 300) -> str:
    payload = json.dumps({
        "model": LOCAL_MODEL,
        "messages": _build_messages(messages),
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["message"]["content"].strip()


def call_local_stream(messages: list[dict], max_tokens: int = 1024,
                      timeout: int = 300) -> Iterator[str]:
    """Streaming Qwen3 — yields text chunks as they arrive."""
    payload = json.dumps({
        "model": LOCAL_MODEL,
        "messages": _build_messages(messages),
        "stream": True,
        "options": {"num_predict": max_tokens, "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for line in resp:
            if line.strip():
                chunk = json.loads(line.decode())
                if not chunk.get("done") and "message" in chunk:
                    yield chunk["message"]["content"]


def call_gemini(prompt: str, context: str = "", timeout: int = 120) -> str:
    """Call Gemini CLI in headless mode (-p flag)."""
    full = f"{context}\n\n{prompt}".strip() if context else prompt
    proc = subprocess.run(
        [GEMINI_BIN, "-p", full, "--yolo"],
        capture_output=True, text=True, timeout=timeout
    )
    output = proc.stdout.strip() or proc.stderr.strip()
    # Strip YOLO mode banner lines that Gemini CLI prints to stdout
    lines = [l for l in output.splitlines()
             if not l.startswith("YOLO mode")]
    return "\n".join(lines).strip()


def route_query(query: str) -> tuple[str, str, str]:
    """Route a raw user query. Returns (type, value, clean_query).

    Explicit prefixes are resolved first (no LLM call):
      !!query  → ("model", "claude",  query)
      !g query → ("model", "gemini",  query)
      /skill … → ("skill", name,      args)

    Everything else goes through Qwen3 for natural-language routing:
      type="skill"  → value=skill_name,          clean_query=args string
      type="model"  → value=local/gemini/claude,  clean_query=query text
    """
    import re as _re

    q = query.strip()

    # Hard overrides — no LLM needed
    if q.startswith("!!"):
        return ("model", "claude", q[2:].strip())
    if q.startswith("!g"):
        return ("model", "gemini", q[2:].strip())
    if q.startswith("/"):
        name = q.split()[0][1:].lower()
        args = " ".join(q.split()[1:])
        return ("skill", name, args)

    # Natural-language routing via Qwen3 (max_tokens=60 keeps it fast)
    messages = [
        {
            "role": "system",
            "content": (
                "Route user messages. Reply with JSON only — no explanation.\n"
                "Skills available: plan, draft, jobs, news, email, remind, "
                "calendar, system, match, browse, graphify\n"
                "Models:\n"
                "  local  — ONLY for trivial one-liners: maths, date/time, yes/no, unit conversion\n"
                "  gemini — everything else: explanations, fintech, payments, stablecoins, crypto, "
                "market trends, company info, analysis, comparisons, general knowledge, conversation\n"
                "  claude — coding, implementing, building, refactoring, debugging, writing scripts\n\n"
                "When in doubt, use gemini not local.\n\n"
                'Examples:\n'
                '"research Airwallex"            → {"type":"skill","value":"plan","args":"research Airwallex"}\n'
                '"plan my trip to Dubai"         → {"type":"skill","value":"plan","args":"trip Dubai"}\n'
                '"what jobs should I apply for"  → {"type":"skill","value":"jobs","args":""}\n'
                '"write a PRD for payments"      → {"type":"skill","value":"draft","args":"prd payments"}\n'
                '"draft a cover letter for Nium" → {"type":"skill","value":"draft","args":"cover Nium"}\n'
                '"how do stablecoins work"       → {"type":"model","value":"gemini","args":""}\n'
                '"explain SWIFT vs correspondent banking" → {"type":"model","value":"gemini","args":""}\n'
                '"what is RBI PA-CB"             → {"type":"model","value":"gemini","args":""}\n'
                '"write a python script"         → {"type":"model","value":"claude","args":""}\n'
                '"what is 15% of 200"            → {"type":"model","value":"local","args":""}\n'
                '"what time is it"               → {"type":"model","value":"local","args":""}'
            ),
        },
        {"role": "user", "content": q},
    ]
    try:
        raw = call_local(messages, max_tokens=60, timeout=30).strip()
        m   = _re.search(r'\{[^}]+\}', raw, _re.DOTALL)
        if m:
            data = json.loads(m.group())
            t    = data.get("type", "model")
            v    = data.get("value", "gemini")
            a    = str(data.get("args", ""))
            if t == "skill":
                return ("skill", v.lower(), a)
            if v in ("claude", "gemini", "local"):
                return ("model", v, q)
    except Exception:
        pass

    # Fallback: keyword-based model routing
    lower = q.lower()
    if any(w in lower for w in ("code", "script", "implement", "build", "refactor", "debug", "fix bug")):
        return ("model", "claude", q)
    return ("model", "gemini", q)


def classify_query(query: str) -> str:
    """Legacy wrapper — use route_query() for new code."""
    _, backend, _ = route_query(query)
    return backend


def call_claude(prompt: str, context: str = "") -> str:
    full = f"{context}\n\n{prompt}".strip() if context else prompt
    proc = subprocess.run(
        [CLAUDE_BIN, "-p", full,
         "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
         "--dangerously-skip-permissions"],
        capture_output=True, text=True, timeout=300
    )
    return proc.stdout.strip() or proc.stderr.strip()


def should_escalate(response: str, iteration: int, max_iters: int) -> bool:
    uncertainty = [
        "i don't know", "i cannot", "i'm not sure", "i am not sure",
        "unable to", "i lack", "beyond my", "i don't have access",
    ]
    low_confidence = any(p in response.lower() for p in uncertainty)
    stuck = iteration >= max_iters - 1
    return low_confidence or stuck
