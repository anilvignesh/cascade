"""
cascade status — live agent dashboard in the terminal.
"""

import json, subprocess, urllib.request, yaml
from pathlib import Path
from datetime import datetime

_CONFIG_PATH = Path(__file__).parent.parent / "config.yml"

C_GREEN  = "\033[92m"
C_BLUE   = "\033[94m"
C_GOLD   = "\033[93m"
C_RED    = "\033[91m"
C_DIM    = "\033[2m"
C_BOLD   = "\033[1m"
C_RESET  = "\033[0m"


def _check_providers() -> list[tuple[str, bool, str]]:
    """Returns list of (name, is_ok, detail)."""
    results = []
    try:
        cfg = yaml.safe_load(_CONFIG_PATH.read_text()).get("providers", {})
    except Exception:
        return []

    for name, pcfg in cfg.items():
        t = pcfg.get("type")
        if t == "cli":
            bin_path = Path(pcfg.get("bin", "")).expanduser()
            ok = bin_path.exists()
            results.append((name, ok, str(bin_path) if ok else "not found"))
        elif t == "ollama":
            try:
                url = pcfg.get("url", "http://localhost:11434/api/chat").replace("/api/chat", "")
                urllib.request.urlopen(url, timeout=2)
                results.append((name, True, pcfg.get("model", "")))
            except Exception:
                results.append((name, False, "ollama offline"))
        elif t == "api":
            import os
            key_env = pcfg.get("api_key_env", "")
            ok = bool(os.environ.get(key_env))
            results.append((name, ok, f"{key_env} {'set' if ok else 'not set'}"))
    return results


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

    # ── Providers ──
    for name, ok, detail in _check_providers():
        status_str = f"{C_GREEN}✓ ready{C_RESET}" if ok else f"{C_RED}✗ {detail}{C_RESET}"
        detail_str = f"  {C_DIM}{detail}{C_RESET}" if ok and detail else ""
        print(f"  {name:<14}{status_str}{detail_str}")

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
