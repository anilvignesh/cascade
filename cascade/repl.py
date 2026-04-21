"""
Cascade interactive REPL — Rich UI with live token counter.
"""

import re
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.live    import Live
from rich.panel   import Panel
from rich.spinner import Spinner
from rich.text    import Text
from rich.markdown import Markdown

from .llm     import call_role_with_stats, get_role_provider, TokenStats
from .memory  import load_context, recall, save, mempalace_save
from .profile import load as load_profile

console = Console()

_PROVIDER_STYLE = {
    "gemini": "bold magenta",
    "claude": "bold blue",
    "local":  "bold yellow",
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


def route_query(raw: str) -> tuple[str, str, str]:
    q = raw.strip()
    if q.startswith("!!"):
        return ("model", "claude", q[2:].strip())
    if q.startswith("!g"):
        return ("model", "gemini", q[2:].strip())
    if q.startswith("/"):
        name = q.split()[0][1:].lower()
        args = " ".join(q.split()[1:])
        return ("skill", name, args)

    try:
        raw_response, _ = call_role_with_stats(
            "interpreter", ROUTING_PROMPT.format(query=q)
        )
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

    lower = q.lower()
    if any(w in lower for w in ("code", "script", "implement", "build", "refactor", "debug", "fix")):
        return ("model", "claude", q)
    return ("model", "gemini", q)


def json_parse(s: str) -> dict:
    import json
    return json.loads(s)


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

    history:      list       = []
    session_msgs: list       = []
    session_total             = TokenStats()

    while True:
        try:
            raw = console.input("[bold green]›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            _print_session_summary(session_total)
            break

        if not raw:
            continue
        if raw.lower() in ("exit", "quit", "q"):
            _print_session_summary(session_total)
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

        try:
            from .skills import run_skill, skill_exists

            route_type, route_value, clean_query = route_query(raw)

            if route_type == "skill" and not skill_exists(route_value):
                route_type, route_value, clean_query = "model", "gemini", raw

            if route_type == "skill":
                memory  = recall(clean_query or raw)
                context = _build_context(session_msgs, memory)
                console.print(f"  [dim]/{route_value}[/]\n")
                response = run_skill(route_value, clean_query, context)
                console.print(Panel(
                    Markdown(response),
                    title=f"[dim]/{route_value}[/]",
                    border_style="dim",
                ))
                save(raw, response, f"skill:{route_value}")
                mempalace_save(raw, response, f"skill:{route_value}")
                history.append((raw, response, f"skill:{route_value}"))
                console.print()
                continue

            memory  = recall(raw)
            context = _build_context(session_msgs, memory)
            role    = "coder" if route_value == "claude" else "researcher"
            provider = get_role_provider(role)
            style    = _PROVIDER_STYLE.get(provider, "dim")
            label    = route_value.capitalize()

            # Spinner while waiting
            response, stats = None, TokenStats()
            with Live(
                Spinner("dots", text=f" [dim]{label} thinking...[/]"),
                console=console, refresh_per_second=12, transient=True
            ):
                response, stats = call_role_with_stats(role, clean_query, context)

            session_total = session_total + stats
            tok_str      = _fmt_tokens(stats)
            ses_str      = _fmt_session(session_total)

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
            mempalace_save(raw, response, route_value)
            history.append((raw, response, route_value))

        except KeyboardInterrupt:
            console.print("\n[dim]interrupted[/]\n")
        except Exception as e:
            from rich.markup import escape
            console.print(f"[red]Error: {escape(str(e))}[/]\n")


def _print_session_summary(total: TokenStats):
    console.print()
    if total.total:
        parts = [f"[dim]session total: {total.total:,} tokens"]
        if total.cost_usd:
            parts.append(f"${total.cost_usd:.4f}[/]")
        else:
            parts.append("[/]")
        console.print("  " + "  ".join(parts))
    console.print("[dim]bye[/]\n")
