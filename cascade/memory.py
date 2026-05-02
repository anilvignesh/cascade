"""
Three-layer memory system:

  context.md  (ROM)    — static facts, always injected. User edits this.
  session_msgs (RAM)   — current session, in-memory only, zero latency.
  Chroma       (LTM)   — long-term vector store. Written by local LLM after
                         session ends (background thread). Semantic search
                         at session start to pull relevant past context.

On session exit:
  qwen3-fast reads session_msgs → extracts structured memories → Chroma.
  Runs async — user's exit is instant.
"""

import json, re, subprocess, threading
from datetime import datetime
from pathlib import Path
from typing import Iterator

import yaml

_CONFIG_PATH    = Path(__file__).parent.parent / "config.yml"
_context_cache: str = ""
_chroma_client  = None
_chroma_col     = None

_CONSOLIDATE_PROMPT = """\
You are a memory agent. Read this conversation and extract key memories worth keeping.

Output a JSON array only — no explanation, no markdown:
[
  {{"type": "fact",       "content": "...", "tags": ["tag1", "tag2"]}},
  {{"type": "decision",   "content": "...", "tags": ["tag1", "tag2"]}},
  {{"type": "preference", "content": "...", "tags": ["tag1", "tag2"]}},
  {{"type": "built",      "content": "...", "tags": ["tag1", "tag2"]}}
]

Types:
  fact       — something learned about the user, system, or domain
  decision   — a choice made during the session
  preference — how the user likes things done
  built      — something that was created or changed

Only include high-value entries. Skip small talk. Max 8 entries.

Session:
{session}"""


# ── Config ────────────────────────────────────────────────────────────────────

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
    global _context_cache
    if _context_cache:
        return _context_cache
    _, ctx_path = _paths()
    _context_cache = ctx_path.read_text().strip()
    return _context_cache


# ── RAM — session_msgs ────────────────────────────────────────────────────────
# Managed by repl.py — no persistence needed here.


# ── LTM — Chroma vector store ─────────────────────────────────────────────────

def _chroma() -> tuple:
    """Lazy-init Chroma client and collection. Returns (client, collection) or (None, None)."""
    global _chroma_client, _chroma_col
    if _chroma_col is not None:
        return _chroma_client, _chroma_col
    try:
        import chromadb
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        chroma_path = Path("~/.cascade/chroma").expanduser()
        chroma_path.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(chroma_path))
        _chroma_col    = _chroma_client.get_or_create_collection(
            name               = "cascade_memory",
            embedding_function = DefaultEmbeddingFunction(),
            metadata           = {"hnsw:space": "cosine"},
        )
        return _chroma_client, _chroma_col
    except Exception:
        return None, None


def chroma_search(query: str, n: int = 4) -> str:
    """Semantic search over long-term memory. Returns relevant past entries."""
    _, col = _chroma()
    if col is None:
        return ""
    try:
        if col.count() == 0:
            return ""
        results = col.query(query_texts=[query], n_results=min(n, col.count()))
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        out = []
        for doc, meta in zip(docs, metas):
            ts   = meta.get("timestamp", "")
            kind = meta.get("type", "")
            out.append(f"[{kind} {ts}] {doc}")
        return "\n".join(out)[:1200]
    except Exception:
        return ""


def chroma_save(content: str, meta: dict):
    """Save a single memory entry to Chroma."""
    _, col = _chroma()
    if col is None:
        return
    try:
        uid = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        col.add(documents=[content], metadatas=[meta], ids=[uid])
    except Exception:
        pass


# ── HDD — memory.md (keyword fallback) ───────────────────────────────────────

def _keyword_search(query: str, limit: int = 2) -> str:
    mem_path, _ = _paths()
    raw = mem_path.read_text().strip()
    if not raw:
        return ""
    entries = re.split(r'\n---\n', raw)
    words   = set(query.lower().split())
    scored  = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        score = sum(1 for w in words if w in entry.lower())
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return "\n\n".join(e for _, e in scored[:limit])[:600]


def _keyword_save(query: str, response: str, backend: str):
    mem_path, _ = _paths()
    entry = (
        f"[{backend}] {datetime.now():%Y-%m-%d %H:%M}\n"
        f"Q: {query[:300]}\n"
        f"A: {response[:800]}"
    )
    with mem_path.open("a") as f:
        f.write(f"\n---\n{entry}")


# ── Session consolidation (runs in background on exit) ────────────────────────

def consolidate_session(session_msgs: list[dict]):
    """
    Called on session exit. Runs in a background thread — non-blocking.
    Local LLM reads the session, extracts memories, writes to Chroma.
    """
    if not session_msgs:
        return

    def _run():
        try:
            session_text = "\n".join(
                f"{'User' if m['role'] == 'user' else 'Cascade'}: {m['content'][:600]}"
                for m in session_msgs
            )
            if len(session_text) < 100:
                return

            from .llm import call_role
            raw = call_role("local_chat",
                            _CONSOLIDATE_PROMPT.format(session=session_text[:6000]))

            m = re.search(r'\[.*\]', raw, re.DOTALL)
            if not m:
                return
            entries = json.loads(m.group())
            if not isinstance(entries, list):
                return

            ts = datetime.now().strftime("%Y-%m-%d")
            saved = 0
            for entry in entries:
                if not isinstance(entry, dict) or "content" not in entry:
                    continue
                content = entry["content"].strip()
                if not content:
                    continue
                chroma_save(content, {
                    "type":      entry.get("type", "fact"),
                    "tags":      ",".join(entry.get("tags", [])),
                    "timestamp": ts,
                    "source":    "session",
                })
                saved += 1

            if saved:
                print(f"\n  [memory] {saved} memories saved to long-term store")
        except Exception:
            pass  # Memory consolidation is best-effort

    threading.Thread(target=_run, daemon=True).start()


# ── Combined recall ────────────────────────────────────────────────────────────

def recall(query: str) -> dict[str, str]:
    """Pull from LTM (Chroma semantic) and HDD (keyword fallback)."""
    ltm = chroma_search(query)
    hdd = _keyword_search(query) if not ltm else ""  # skip keyword if LTM has results
    return {"hdd": hdd, "ram": ltm}


def save(query: str, response: str, backend: str):
    """Per-turn save to keyword store (fast). Chroma updated only on session end."""
    _keyword_save(query, response, backend)


# ── Legacy shims ──────────────────────────────────────────────────────────────

def mempalace_search(query: str) -> str:
    return chroma_search(query)

def mempalace_save(query: str, response: str, backend: str):
    pass  # Replaced by session consolidation
