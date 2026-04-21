"""
cascade status — live agent dashboard in the terminal.
"""

import json, subprocess, urllib.request
from pathlib import Path
from datetime import datetime

C_GREEN  = "\033[92m"
C_BLUE   = "\033[94m"
C_GOLD   = "\033[93m"
C_RED    = "\033[91m"
C_DIM    = "\033[2m"
C_BOLD   = "\033[1m"
C_RESET  = "\033[0m"


def _check_ollama() -> tuple[bool, list[str]]:
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        models = [l.split()[0] for l in r.stdout.splitlines()[1:] if l.strip()]
        return True, models
    except Exception:
        return False, []


def _check_mempalace() -> str:
    try:
        r = subprocess.run(["mempalace", "status"], capture_output=True, text=True, timeout=5)
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        return lines[0] if lines else "running"
    except Exception:
        return "unavailable"


def _agent_state() -> dict:
    state_file = Path.home() / "cascade" / ".agent" / "worker-state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            pass
    return {}


def _recent_memory() -> list[str]:
    try:
        r = subprocess.run(
            ["mempalace", "search", "cascade", "--limit", "5"],
            capture_output=True, text=True, timeout=8
        )
        return [l for l in r.stdout.splitlines()
                if l.strip() and not l.startswith(("Search", "===", "---"))][:8]
    except Exception:
        return []


def show():
    now = datetime.now().strftime("%A %d %B %Y  ·  %H:%M")
    print(f"\n{C_BOLD}{C_GREEN}◆ CASCADE STATUS{C_RESET}  {C_DIM}{now}{C_RESET}\n")

    # ── Ollama ──
    ok, models = _check_ollama()
    status_str = f"{C_GREEN}✓ running{C_RESET}" if ok else f"{C_RED}✗ offline{C_RESET}"
    model_str  = f"  {C_DIM}{', '.join(models)}{C_RESET}" if models else ""
    print(f"  Ollama       {status_str}{model_str}")

    # ── MemPalace ──
    mp = _check_mempalace()
    mp_ok = "unavailable" not in mp
    mp_color = C_GREEN if mp_ok else C_RED
    print(f"  MemPalace    {mp_color}{mp}{C_RESET}")

    # ── Agent state ──
    state = _agent_state()
    if state:
        s = state.get("status", "?")
        b = state.get("backend", "?")
        t = state.get("task", "")[:55]
        e = state.get("elapsed_s", "?")
        color = C_GOLD if s == "processing" else C_GREEN if s == "complete" else C_DIM
        print(f"  Agent        {color}{s}{C_RESET}  [{b}]  {C_DIM}{t}  ({e}s){C_RESET}")
    else:
        print(f"  Agent        {C_DIM}idle{C_RESET}")

    # ── Recent memory ──
    recent = _recent_memory()
    if recent:
        print(f"\n  {C_DIM}Recent exchanges:{C_RESET}")
        for line in recent[:5]:
            print(f"  {C_DIM}{line[:72]}{C_RESET}")

    print()
