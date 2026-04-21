"""
Cascade interactive REPL.
Type queries → Qwen3 (streaming) or Claude responds.
Session conversation kept in memory. All exchanges saved to MemPalace.
"""

import sys, subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".jarvis"))

from .llm     import call_local, call_local_stream, call_claude, call_gemini, route_query
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
        f"Q: {query[:500]}\n"
        f"A: {response[:2000]}"
    )
    try:
        subprocess.run(
            ["mempalace", "add", "--content", entry,
             "--tags", f"cascade,{backend}"],
            capture_output=True, timeout=8
        )
    except Exception:
        pass


def _build_local_messages(query: str, session_msgs: list[dict], mem: str) -> list[dict]:
    profile = load_profile()
    messages = [{"role": "system", "content": SYSTEM}]
    if profile:
        messages.append({"role": "user",      "content": f"User profile:\n{profile}"})
        messages.append({"role": "assistant",  "content": "Got it."})
    if mem:
        messages.append({"role": "user",      "content": f"Relevant memory:\n{mem}"})
        messages.append({"role": "assistant",  "content": "Noted."})
    messages.extend(session_msgs[-8:])
    messages.append({"role": "user", "content": query})
    return messages


def ask_local(query: str, session_msgs: list[dict], mem: str = "") -> str:
    """Non-streaming Qwen3 — used by Telegram bot and other callers."""
    messages = _build_local_messages(query, session_msgs, mem)
    return call_local(messages, max_tokens=1024)


def ask_local_stream(query: str, session_msgs: list[dict], mem: str):
    """Streaming Qwen3 — yields chunks for real-time output in REPL."""
    messages = _build_local_messages(query, session_msgs, mem)
    return call_local_stream(messages, max_tokens=1024)


def _build_cloud_context(session_msgs: list[dict], mem: str,
                          persona: str = "Cascade, a local-first AI assistant") -> str:
    profile = load_profile()
    ctx_parts = [
        f"You are {persona}.\n"
        f"Be direct and concise. Today: {datetime.today():%A %d %B %Y}."
    ]
    if profile:
        ctx_parts.append(f"User profile:\n{profile}")
    if mem:
        ctx_parts.append(f"Relevant memory:\n{mem}")
    if session_msgs:
        turns = "\n".join(
            f"{'User' if m['role']=='user' else 'Cascade'}: {m['content'][:300]}"
            for m in session_msgs[-8:]
        )
        ctx_parts.append(f"Recent conversation:\n{turns}")
    return "\n\n".join(ctx_parts)


def ask_gemini(query: str, session_msgs: list[dict], mem: str) -> str:
    context = _build_cloud_context(session_msgs, mem)
    return call_gemini(query, context=context)


def ask_claude(query: str, session_msgs: list[dict], mem: str) -> str:
    context = _build_cloud_context(session_msgs, mem)
    return call_claude(query, context=context)


def _build_skill_context(query: str, session_msgs: list[dict], mem: str) -> str:
    parts = []
    if mem:
        parts.append(f"Relevant memory:\n{mem}")
    if session_msgs:
        turns = "\n".join(
            f"{'User' if m['role']=='user' else 'Cascade'}: {m['content'][:200]}"
            for m in session_msgs[-4:]
        )
        parts.append(f"Recent conversation:\n{turns}")
    return "\n\n".join(parts)


def run():
    print(f"\n{C_BOLD}{C_GREEN}◆ CASCADE{C_RESET}  "
          f"{C_DIM}Qwen3 · Gemini · Claude  ·  !! claude  ·  !g gemini  ·  /skill  ·  exit{C_RESET}\n")

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

        try:
            from .skills import run_skill, skill_exists

            # Single routing call — handles /skill, !!, !g, and natural language
            route_type, route_value, clean_query = route_query(raw)

            # Validate skill exists; fall back to model if not
            if route_type == "skill" and not skill_exists(route_value):
                route_type, route_value, clean_query = "model", "gemini", raw

            if route_type == "skill":
                mem     = mem_search(clean_query or raw)
                context = _build_skill_context(raw, session_msgs, mem)
                print(f"  {C_DIM}[/{route_value}]{C_RESET}\n", flush=True)
                response = run_skill(route_value, clean_query, context)
                print(response, "\n")
                mem_save(raw, response, f"skill:{route_value}")
                history.append((raw, response, f"skill:{route_value}"))
                continue

            # Model routing
            query = clean_query
            mem   = mem_search(query)

            C_PURPLE = "\033[95m"
            mode = route_value
            if mode == "claude":
                label = f"{C_BLUE}Claude{C_RESET}"
            elif mode == "gemini":
                label = f"{C_PURPLE}Gemini{C_RESET}"
            else:
                label = f"{C_GOLD}Qwen3{C_RESET}"
            print(f"  {C_DIM}[{label}{C_DIM}]{C_RESET}\n", flush=True)

            if mode == "claude":
                response = ask_claude(query, session_msgs, mem)
                print(response, "\n")
                backend = "claude"
            elif mode == "gemini":
                response = ask_gemini(query, session_msgs, mem)
                print(response, "\n")
                backend = "gemini"
            else:
                # Streaming — print chunks as they arrive
                chunks = []
                for chunk in ask_local_stream(query, session_msgs, mem):
                    print(chunk, end="", flush=True)
                    chunks.append(chunk)
                print("\n")
                response = "".join(chunks)
                backend = "local"

            # Update session conversation (multi-turn)
            session_msgs.append({"role": "user",      "content": query})
            session_msgs.append({"role": "assistant",  "content": response})

            mem_save(query, response, backend)
            history.append((query, response, backend))

        except KeyboardInterrupt:
            print(f"\n{C_DIM}interrupted{C_RESET}\n")
        except Exception as e:
            print(f"\033[91mError: {e}\033[0m\n")
