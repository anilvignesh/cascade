"""
Cascade interactive REPL — Rich UI, live token counter, input queue.
"""

import re, sys, queue, threading
from datetime import datetime

from rich.console  import Console
from rich.live     import Live
from rich.panel    import Panel
from rich.spinner  import Spinner
from rich.markdown import Markdown

from .llm    import call_role_with_stats, get_role_provider, TokenStats
from .memory import load_context, recall, save, consolidate_session
from .profile import load as load_profile

console = Console()

_PROVIDER_STYLE = {
    "gemini":     "bold magenta",
    "claude":     "bold blue",
    "local":      "bold yellow",
    "groq":       "bold cyan",
    "cerebras":   "bold green",
    "openrouter": "bold white",
}

_ROLE_MAP = {
    "claude":     "coder",
    "gemini":     "researcher",
    "groq":       "general",
    "cerebras":   "general",
    "openrouter": "general",
    "local":      "local_chat",
}

ROUTING_PROMPT = """\
Route user messages. Reply with JSON only — no explanation.

Skills available: plan, draft, jobs, news, email, remind, calendar, system, browse, graphify
Models:
  groq   — quick questions, summaries, factual lookups, general chat (fast, free)
  gemini — deep research, long analysis, document review
  claude — coding, implementing, debugging, architecture, scripts
  local  — private or sensitive queries, anything that must stay offline

Prefer groq for most things. Use claude only for code tasks. Use local for private/sensitive.

Examples:
"research Airwallex"         → {{"type":"skill","value":"plan","args":"research Airwallex"}}
"write a python script"      → {{"type":"model","value":"claude","args":""}}
"how do stablecoins work"    → {{"type":"model","value":"groq","args":""}}
"explain this privately"     → {{"type":"model","value":"local","args":""}}
"draft a cover letter"       → {{"type":"skill","value":"draft","args":"cover letter"}}

User message: {query}"""


def _fmt_tokens(stats: TokenStats) -> str:
    if not stats.total:
        return ""
    parts = [f"↑{stats.input:,} ↓{stats.output:,}"]
    if stats.cost_usd:
        parts.append(f"${stats.cost_usd:.4f}")
    return "  ".join(parts)


def _fmt_session(total: TokenStats) -> str:
    if not total.total:
        return ""
    s = f"session {total.total:,} tokens"
    if total.cost_usd:
        s += f"  ${total.cost_usd:.4f}"
    return s


_CODE_WORDS   = re.compile(r'\b(code|script|implement|build|refactor|debug|fix|function|class|program|compile|deploy|api|endpoint)\b')
_GEMINI_WORDS = re.compile(r'\b(research|analyse|analyze|summarise|summarize|document|report|compare|deep.dive)\b')
_LOCAL_WORDS  = re.compile(r'\b(private|privately|offline|sensitive|confidential|secret)\b')

def route_query(raw: str) -> tuple[str, str, str]:
    q = raw.strip()

    # ── Explicit overrides ────────────────────────────────────────────────────
    if q.startswith("!!"):
        return ("model", "claude", q[2:].strip())
    if q.startswith("!g"):
        return ("model", "gemini", q[2:].strip())
    if q.startswith("!l"):
        return ("model", "local", q[2:].strip())
    if q.startswith("/"):
        name = q.split()[0][1:].lower()
        args = " ".join(q.split()[1:])
        return ("skill", name, args)

    # ── Fast rule-based routing (no API call) ─────────────────────────────────
    lower = q.lower()
    if _LOCAL_WORDS.search(lower):
        return ("model", "local", q)
    if _CODE_WORDS.search(lower):
        return ("model", "claude", q)
    if _GEMINI_WORDS.search(lower):
        return ("model", "gemini", q)

    # ── LLM routing only for skill detection ─────────────────────────────────
    # Only call the interpreter if the query might be a skill invocation
    _SKILL_HINTS = {"plan", "draft", "job", "news", "email", "remind",
                    "calendar", "browse", "graphify", "schedule", "search"}
    if any(w in lower for w in _SKILL_HINTS):
        try:
            raw_response, _ = call_role_with_stats(
                "interpreter", ROUTING_PROMPT.format(query=q)
            )
            m = re.search(r'\{[^}]+\}', raw_response, re.DOTALL)
            if m:
                import json
                data = json.loads(m.group())
                t = data.get("type", "model")
                v = data.get("value", "groq")
                a = str(data.get("args", ""))
                if t == "skill":
                    return ("skill", v.lower(), a)
                if v in _ROLE_MAP:
                    return ("model", v, q)
        except Exception:
            pass

    # ── Default: Gemini (quality, already paid) ──────────────────────────────
    return ("model", "gemini", q)


def _build_context(session_msgs: list[dict], memory: dict) -> str:
    rom     = load_context()
    hdd     = memory.get("hdd")
    ram     = memory.get("ram")
    profile = load_profile()

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


def _print_session_summary(total: TokenStats, session_msgs: list):
    console.print()
    if total.total:
        s = f"[dim]session total: {total.total:,} tokens"
        if total.cost_usd:
            s += f"  ${total.cost_usd:.4f}"
        console.print(f"  {s}[/]")
    console.print("[dim]bye[/]\n")
    consolidate_session(session_msgs)  # async — returns immediately


def _prompt(is_busy: bool, queued: int) -> str:
    if is_busy and queued:
        return f"\033[2m  [{queued} queued] +\033[0m "
    if is_busy:
        return "\033[2m  [+]\033[0m "
    return "\033[1m\033[92m›\033[0m "


def run():
    console.print()
    console.print(Panel(
        "[bold green]◆ CASCADE[/]   [dim]Gemini · Claude  ·  "
        "[bold]!![/] claude  ·  [bold]!g[/] gemini  ·  "
        "[bold]/skill[/]  ·  exit[/]",
        border_style="green",
        padding=(0, 2),
    ))
    console.print()

    history:       list       = []
    session_msgs:  list       = []
    session_total              = TokenStats()

    # ── Input queue — background thread collects input, main thread processes ──
    work_q   = queue.Queue()
    is_busy  = threading.Event()

    def _input_collector():
        while True:
            try:
                sys.stdout.write(_prompt(is_busy.is_set(), work_q.qsize()))
                sys.stdout.flush()
                line = sys.stdin.readline()
                if not line:
                    work_q.put(None)
                    break
                work_q.put(line.rstrip("\n"))
            except (EOFError, KeyboardInterrupt):
                work_q.put(None)
                break

    threading.Thread(target=_input_collector, daemon=True).start()

    while True:
        raw = work_q.get()

        if raw is None:
            _print_session_summary(session_total, session_msgs)
            break

        raw = raw.strip()
        if not raw:
            continue
        if raw.lower() in ("exit", "quit", "q"):
            _print_session_summary(session_total, session_msgs)
            break
        if raw.lower() == "history":
            if not history:
                console.print("  [dim]no history yet[/]")
            for i, (q, _, b) in enumerate(history[-10:], 1):
                console.print(f"  [dim]{i}. [{b}] {q[:65]}[/]")
            console.print()
            continue
        if raw.lower() == "clear":
            history.clear()
            session_msgs.clear()
            session_total = TokenStats()
            console.print("[dim]cleared[/]\n")
            continue

        is_busy.set()

        try:
            from .skills import run_skill, skill_exists

            # ── Immediate feedback — routing spinner shown before Gemini call ──
            with Live(
                Spinner("dots", text=" [dim]routing...[/]"),
                console=console, refresh_per_second=12, transient=True
            ):
                route_type, route_value, clean_query = route_query(raw)

            if route_type == "skill" and not skill_exists(route_value):
                route_type, route_value, clean_query = "model", "gemini", raw

            if route_type == "skill":
                memory  = recall(clean_query or raw)
                context = _build_context(session_msgs, memory)
                with Live(
                    Spinner("dots", text=f" [dim]/{route_value}...[/]"),
                    console=console, refresh_per_second=12, transient=True
                ):
                    response = run_skill(route_value, clean_query, context)
                console.print(Panel(
                    Markdown(response),
                    title=f"[dim]/{route_value}[/]",
                    border_style="dim",
                ))
                save(raw, response, f"skill:{route_value}")
                history.append((raw, response, f"skill:{route_value}"))
                console.print()
                is_busy.clear()
                continue

            memory   = recall(raw)
            context  = _build_context(session_msgs, memory)
            role     = _ROLE_MAP.get(route_value, "general")
            provider = get_role_provider(role)
            style    = _PROVIDER_STYLE.get(provider, "dim")
            label    = route_value.capitalize()

            # ── Model call spinner ──
            with Live(
                Spinner("dots", text=f" [dim]{label} thinking...[/]"),
                console=console, refresh_per_second=12, transient=True
            ):
                response, stats = call_role_with_stats(role, clean_query, context)

            session_total = session_total + stats
            tok_str       = _fmt_tokens(stats)
            ses_str       = _fmt_session(session_total)

            console.print(Panel(
                Markdown(response),
                title=f"[{style}]{label}[/]",
                subtitle=f"[dim]{tok_str}[/]" if tok_str else None,
                border_style="dim",
                padding=(1, 2),
            ))
            if ses_str:
                console.print(f"  [dim]{ses_str}[/]")
            console.print()

            session_msgs.append({"role": "user",      "content": clean_query})
            session_msgs.append({"role": "assistant",  "content": response})

            save(raw, response, route_value)
            history.append((raw, response, route_value))

        except KeyboardInterrupt:
            console.print("\n[dim]interrupted[/]\n")
        except Exception as e:
            from rich.markup import escape
            console.print(f"[red]Error: {escape(str(e))}[/]\n")

        is_busy.clear()

        # Show how many are queued
        queued = work_q.qsize()
        if queued:
            console.print(f"  [dim]{queued} queued[/]\n")
