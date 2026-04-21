"""
Cascade interactive REPL.
Type queries, get responses from Qwen3 or Claude depending on complexity.
All exchanges saved to MemPalace — shared context across both models.
"""

import sys, subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".jarvis"))

from .llm   import call_local, call_claude
from .state import WorkerState, Status

C_GREEN  = "\033[92m"
C_BLUE   = "\033[94m"
C_GOLD   = "\033[93m"
C_DIM    = "\033[2m"
C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"


def mem_search(query: str) -> str:
    try:
        r = subprocess.run(
            ["mempalace", "search", query, "--limit", "3"],
            capture_output=True, text=True, timeout=8
        )
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and not l.startswith(("Search", "===", "---"))]
        return "\n".join(lines)[:800]
    except Exception:
        return ""


def mem_save(query: str, response: str, backend: str):
    entry = (
        f"[cascade/{backend}] {datetime.now():%Y-%m-%d %H:%M}\n"
        f"Q: {query[:200]}\n"
        f"A: {response[:600]}"
    )
    try:
        subprocess.run(
            ["mempalace", "add", "--content", entry,
             "--tags", f"cascade,{backend}"],
            capture_output=True, timeout=8
        )
    except Exception:
        pass


def route(query: str) -> str:
    """Decide local or claude. Reuses jarvis router if available."""
    try:
        from agents.router import route as _route
        return _route(query)
    except Exception:
        pass
    # Fallback: simple keyword check
    claude_kw = ["draft", "write", "build", "create", "code", "script",
                 "refactor", "fix", "implement", "email", "execute"]
    q = query.lower()
    if any(k in q for k in claude_kw):
        return "claude"
    return "local"


def ask(query: str) -> tuple[str, str]:
    """Returns (response, backend_label)."""
    mem = mem_search(query)
    context = f"Memory context:\n{mem}\n\n" if mem else ""

    mode = route(query)

    if mode == "claude":
        prompt = (
            f"{context}"
            f"You are Cascade, Anil's AI assistant. Senior PM, cross-border payments.\n"
            f"Be direct. Today: {datetime.today():%A %d %B %Y}.\n\n"
            f"{query}"
        )
        response = call_claude(prompt)
        return response, "claude"
    else:
        system = (
            "You are Cascade, Anil Vignesh's AI assistant. "
            "Senior PM in cross-border payments, job hunting in Dubai. "
            "Be direct and concise. Always respond in English only."
        )
        messages = [
            {"role": "system", "content": system},
        ]
        if mem:
            messages.append({"role": "user",      "content": f"Memory context:\n{mem}"})
            messages.append({"role": "assistant",  "content": "Got it, I have that context."})
        messages.append({"role": "user", "content": query})

        response = call_local(messages, max_tokens=1024)
        return response, "local"


def run():
    print(f"\n{C_BOLD}{C_GREEN}◆ CASCADE{C_RESET}  {C_DIM}local-first AI · type 'exit' to quit{C_RESET}\n")

    history = []

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
            for i, (q, _, b) in enumerate(history[-10:], 1):
                print(f"  {C_DIM}{i}. [{b}] {q[:60]}{C_RESET}")
            continue
        if raw.lower() == "clear":
            history.clear()
            print(f"{C_DIM}history cleared{C_RESET}")
            continue

        # Force escalation with !! prefix
        force_claude = raw.startswith("!!")
        query = raw[2:].strip() if force_claude else raw

        try:
            # Check for skill invocation (/skillname ...)
            from .skills import detect_skill, run_skill
            skill_name = detect_skill(query)
            if skill_name:
                skill_query = " ".join(query.split()[1:])
                print(f"  {C_DIM}[skill: {skill_name}]{C_RESET}\n", flush=True)
                response = run_skill(skill_name, skill_query)
                print(response)
                print()
                mem_save(query, response, f"skill:{skill_name}")
                history.append((query, response, f"skill:{skill_name}"))
                continue

            mode_hint = "claude" if force_claude else route(query)
            label = f"{C_BLUE}Claude{C_RESET}" if mode_hint == "claude" else f"{C_GOLD}Qwen3{C_RESET}"
            print(f"  {C_DIM}[{label}{C_DIM}]{C_RESET}", end="\n\n", flush=True)

            if force_claude:
                response = call_claude(query)
                backend = "claude"
            else:
                response, backend = ask(query)

            print(response)
            print()

            mem_save(query, response, backend)
            history.append((query, response, backend))

        except KeyboardInterrupt:
            print(f"\n{C_DIM}interrupted{C_RESET}")
        except Exception as e:
            print(f"\033[91mError: {e}\033[0m")
