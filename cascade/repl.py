"""
Cascade interactive REPL.
Gemini interprets and routes every query.
Shared context injected into every model call.
"""

import re
from datetime import datetime
from pathlib import Path

from .llm     import call_role, get_role_provider
from .memory  import load_context, recall, save, mempalace_save
from .profile import load as load_profile

C_GREEN  = "\033[92m"
C_BLUE   = "\033[94m"
C_GOLD   = "\033[93m"
C_PURPLE = "\033[95m"
C_DIM    = "\033[2m"
C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"

_PROVIDER_COLORS = {
    "gemini": C_PURPLE,
    "claude": C_BLUE,
    "local":  C_GOLD,
}

ROUTING_PROMPT = """\
Route user messages. Reply with JSON only — no explanation.

Skills available: plan, draft, jobs, news, email, remind, calendar, system, browse, graphify
Models:
  gemini — research, analysis, explanations, general conversation
  claude — coding, implementing, debugging, architecture, scripts

When in doubt, use gemini.

Examples:
"research Airwallex"         → {{"type":"skill","value":"plan","args":"research Airwallex"}}
"write a python script"      → {{"type":"model","value":"claude","args":""}}
"how do stablecoins work"    → {{"type":"model","value":"gemini","args":""}}
"draft a cover letter"       → {{"type":"skill","value":"draft","args":"cover letter"}}

User message: {query}"""



def route_query(raw: str) -> tuple[str, str, str]:
    """Returns (type, value, clean_query). type = 'model' | 'skill'."""
    q = raw.strip()

    # Hard overrides — no LLM needed
    if q.startswith("!!"):
        return ("model", "claude", q[2:].strip())
    if q.startswith("!g"):
        return ("model", "gemini", q[2:].strip())
    if q.startswith("/"):
        name = q.split()[0][1:].lower()
        args = " ".join(q.split()[1:])
        return ("skill", name, args)

    # Gemini interprets intent
    try:
        raw_response = call_role("interpreter", ROUTING_PROMPT.format(query=q))
        m = re.search(r'\{[^}]+\}', raw_response, re.DOTALL)
        if m:
            data = json_parse(m.group())
            t = data.get("type", "model")
            v = data.get("value", "gemini")
            a = str(data.get("args", ""))
            if t == "skill":
                return ("skill", v.lower(), a)
            if v in ("claude", "gemini", "local"):
                return ("model", v, q)
    except Exception:
        pass

    # Keyword fallback
    lower = q.lower()
    if any(w in lower for w in ("code", "script", "implement", "build", "refactor", "debug", "fix")):
        return ("model", "claude", q)
    return ("model", "gemini", q)


def json_parse(s: str) -> dict:
    import json
    return json.loads(s)


def _build_context(session_msgs: list[dict], memory: dict) -> str:
    rom     = load_context()       # context.md  — always present
    hdd     = memory.get("hdd")    # memory.md   — past Q&A keyword match
    ram     = memory.get("ram")    # MemPalace   — semantic recall
    profile = load_profile()       # MemPalace profile (silent if down)

    parts = [
        f"You are Cascade, an AI assistant.\n"
        f"Be direct and concise. Today: {datetime.today():%A %d %B %Y}."
    ]
    if rom:     parts.append(f"Persistent context:\n{rom}")
    if profile: parts.append(f"User profile:\n{profile}")
    if ram:     parts.append(f"Semantic memory:\n{ram}")
    if hdd:     parts.append(f"Past conversations:\n{hdd}")
    if session_msgs:
        turns = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Cascade'}: {m['content'][:300]}"
            for m in session_msgs[-8:]
        )
        parts.append(f"This session:\n{turns}")
    return "\n\n".join(parts)


def run():
    print(f"\n{C_BOLD}{C_GREEN}◆ CASCADE{C_RESET}  "
          f"{C_DIM}Gemini · Claude  ·  !! claude  ·  !g gemini  ·  /skill  ·  exit{C_RESET}\n")

    history:      list = []
    session_msgs: list = []

    while True:
        try:
            raw = input(f"{C_GREEN}›{C_RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C_DIM}bye{C_RESET}")
            break

        if not raw:
            continue
        if raw.lower() in ("exit", "quit", "q"):
            print(f"{C_DIM}bye{C_RESET}")
            break
        if raw.lower() == "history":
            if not history:
                print(f"  {C_DIM}no history yet{C_RESET}")
            for i, (q, _, b) in enumerate(history[-10:], 1):
                print(f"  {C_DIM}{i}. [{b}] {q[:65]}{C_RESET}")
            print()
            continue
        if raw.lower() == "clear":
            history.clear()
            session_msgs.clear()
            print(f"{C_DIM}cleared{C_RESET}\n")
            continue

        try:
            from .skills import run_skill, skill_exists

            route_type, route_value, clean_query = route_query(raw)

            if route_type == "skill" and not skill_exists(route_value):
                route_type, route_value, clean_query = "model", "gemini", raw

            if route_type == "skill":
                memory  = recall(clean_query or raw)
                context = _build_context(session_msgs, memory)
                print(f"  {C_DIM}[/{route_value}]{C_RESET}\n", flush=True)
                response = run_skill(route_value, clean_query, context)
                print(response, "\n")
                save(raw, response, f"skill:{route_value}")
                mempalace_save(raw, response, f"skill:{route_value}")
                history.append((raw, response, f"skill:{route_value}"))
                continue

            memory  = recall(raw)
            context = _build_context(session_msgs, memory)

            role  = "coder" if route_value == "claude" else "researcher"
            color = _PROVIDER_COLORS.get(get_role_provider(role), C_DIM)
            label = f"{color}{route_value.capitalize()}{C_RESET}"
            print(f"  {C_DIM}[{label}{C_DIM}]{C_RESET}\n", flush=True)

            response = call_role(role, clean_query, context)
            print(response, "\n")

            session_msgs.append({"role": "user",      "content": clean_query})
            session_msgs.append({"role": "assistant",  "content": response})

            save(raw, response, route_value)
            mempalace_save(raw, response, route_value)
            history.append((raw, response, route_value))

        except KeyboardInterrupt:
            print(f"\n{C_DIM}interrupted{C_RESET}\n")
        except Exception as e:
            print(f"\033[91mError: {e}\033[0m\n")
