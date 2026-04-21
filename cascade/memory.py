"""
Three-layer memory system:

  context.md  (ROM)  — static facts, always injected. User maintains this.
  memory.md   (HDD)  — append-log of past Q&A, keyword-searched each call.
  MemPalace   (RAM)  — semantic graph memory, injected when available.

All three feed into _build_context() in repl.py with distinct roles.
Advanced backends (mem0, Graphiti) can replace the HDD layer via config.yml.
"""

import re, subprocess
from datetime import datetime
from pathlib import Path

import yaml

_CONFIG_PATH    = Path(__file__).parent.parent / "config.yml"
_context_cache: str = ""


# ── Paths ─────────────────────────────────────────────────────────────────────

def _paths() -> tuple[Path, Path]:
    cfg      = yaml.safe_load(_CONFIG_PATH.read_text()).get("memory", {})
    mem_path = Path(cfg.get("path",         "~/.cascade/memory.md")).expanduser()
    ctx_path = Path(cfg.get("context_file", "~/.cascade/context.md")).expanduser()
    mem_path.parent.mkdir(parents=True, exist_ok=True)
    ctx_path.parent.mkdir(parents=True, exist_ok=True)
    if not mem_path.exists(): mem_path.touch()
    if not ctx_path.exists(): ctx_path.touch()
    return mem_path, ctx_path


# ── ROM — context.md ──────────────────────────────────────────────────────────

def load_context() -> str:
    """Static persistent context. Loaded once per session, always injected."""
    global _context_cache
    if _context_cache:
        return _context_cache
    _, ctx_path = _paths()
    _context_cache = ctx_path.read_text().strip()
    return _context_cache


# ── HDD — memory.md ───────────────────────────────────────────────────────────

def search(query: str, limit: int = 3) -> str:
    """Keyword search over memory.md. Returns top matching past entries."""
    mem_path, _ = _paths()
    raw = mem_path.read_text().strip()
    if not raw:
        return ""

    entries = re.split(r'\n---\n', raw)
    words   = set(query.lower().split())

    scored = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        score = sum(1 for w in words if w in entry.lower())
        if score:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return "\n\n".join(e for _, e in scored[:limit])[:1200]


def save(query: str, response: str, backend: str):
    """Append a Q&A entry to memory.md."""
    mem_path, _ = _paths()
    entry = (
        f"[{backend}] {datetime.now():%Y-%m-%d %H:%M}\n"
        f"Q: {query[:500]}\n"
        f"A: {response[:1500]}"
    )
    with mem_path.open("a") as f:
        f.write(f"\n---\n{entry}")


# ── RAM — MemPalace ───────────────────────────────────────────────────────────

def mempalace_search(query: str) -> str:
    """Semantic search via MemPalace. Silent if unavailable."""
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


def mempalace_save(query: str, response: str, backend: str):
    """Persist to MemPalace. Silent if unavailable."""
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


# ── Combined recall (used by repl.py) ─────────────────────────────────────────

def recall(query: str) -> dict[str, str]:
    """Pull from all three layers. Returns dict with keys: hdd, ram."""
    return {
        "hdd": search(query),
        "ram": mempalace_search(query),
    }
