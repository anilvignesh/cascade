"""
Cascade interactive REPL.
Type queries → Qwen3 or Claude responds.
Session conversation kept in memory. All exchanges saved to MemPalace.
"""

import sys, subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".jarvis"))

from .llm     import call_local, call_claude
from .profile import load as load_profile

C_GREEN  = "\033[92m"
C_BLUE   = "\033[94m"
C_GOLD   = "\033[93m"
C_DIM    = "\033[2m"
C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"

SYSTEM = (
    "You are Cascade, a local-first AI assistant. "
    "Be direct and concise. Always respond in English only."
)


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
    try:
        from agents.router import route as _route
        return _route(query)
    except Exception:
        pass
    claude_kw = ["draft", "write", "build", "create", "code", "script",
                 "refactor", "fix", "implement", "email", "execute"]
    if any(k in query.lower() for k in claude_kw):
        return "claude"
    return "local"


def ask_local(query: str, session_msgs: list[dict]) -> str:
    """Call Qwen3 with user profile + session history + relevant memory."""
    profile = load_profile()
    mem     = mem_search(query)

    messages = [{"role": "system", "content": SYSTEM}]
    if profile:
        messages.append({"role": "user",      "content": f"User profile:\n{profile}"})
        messages.append({"role": "assistant",  "content": "Got it."})
    if mem:
        messages.append({"role": "user",      "content": f"Relevant memory:\n{mem}"})
        messages.append({"role": "assistant",  "content": "Noted."})
    messages.extend(session_msgs[-6:])
    messages.append({"role": "user", "content": query})
    return call_local(messages, max_tokens=1024)


def ask_claude(query: str, session_msgs: list[dict]) -> str:
    """Call Claude with user profile + session history + relevant memory."""
    profile = load_profile()
    mem     = mem_search(query)

    ctx_parts = [
        f"You are Cascade, a local-first AI assistant.\n"
        f"Be direct and concise. Today: {datetime.today():%A %d %B %Y}."
    ]
    if profile:
        ctx_parts.append(f"User profile:\n{profile}")
    if mem:
        ctx_parts.append(f"Relevant memory:\n{mem}")
    if session_msgs:
        turns = "\n".join(
            f"{'User' if m['role']=='user' else 'Cascade'}: {m['content'][:300]}"
            for m in session_msgs[-6:]
        )
        ctx_parts.append(f"Recent conversation:\n{turns}")
    return call_claude(query, context="\n\n".join(ctx_parts))


def run():
    print(f"\n{C_BOLD}{C_GREEN}◆ CASCADE{C_RESET}  "
          f"{C_DIM}local-first AI · !! for Claude · /skill · exit{C_RESET}\n")

    history      = []   # (query, response, backend)
    session_msgs = []   # running conversation for multi-turn context

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

        force_claude = raw.startswith("!!")
        query = raw[2:].strip() if force_claude else raw

        try:
            # Skill invocation
            from .skills import detect_skill, run_skill
            skill_name = detect_skill(query)
            if skill_name:
                skill_query = " ".join(query.split()[1:])
                print(f"  {C_DIM}[/{skill_name}]{C_RESET}\n", flush=True)
                response = run_skill(skill_name, skill_query)
                print(response, "\n")
                mem_save(query, response, f"skill:{skill_name}")
                history.append((query, response, f"skill:{skill_name}"))
                continue

            # Route
            mode = "claude" if force_claude else route(query)
            label = f"{C_BLUE}Claude{C_RESET}" if mode == "claude" else f"{C_GOLD}Qwen3{C_RESET}"
            print(f"  {C_DIM}[{label}{C_DIM}]{C_RESET}\n", flush=True)

            if mode == "claude":
                response = ask_claude(query, session_msgs)
                backend  = "claude"
            else:
                response = ask_local(query, session_msgs)
                backend  = "local"

            print(response, "\n")

            # Update session conversation (multi-turn)
            session_msgs.append({"role": "user",      "content": query})
            session_msgs.append({"role": "assistant",  "content": response})

            mem_save(query, response, backend)
            history.append((query, response, backend))

        except KeyboardInterrupt:
            print(f"\n{C_DIM}interrupted{C_RESET}\n")
        except Exception as e:
            print(f"\033[91mError: {e}\033[0m\n")
