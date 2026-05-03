"""
Cascade interactive REPL — Rich UI, live token counter, input queue.
"""

import re, sys, subprocess, queue, threading
from datetime import datetime

from rich.console  import Console
from rich.live     import Live
from rich.panel    import Panel
from rich.spinner  import Spinner
from rich.markdown import Markdown

from .llm    import call_role_with_stats, get_role_provider, TokenStats, _get_registry
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


_CODE_WORDS    = re.compile(r'\b(code|script|implement|build|refactor|debug|fix|function|class|program|compile|deploy|api|endpoint)\b')
_GEMINI_WORDS  = re.compile(r'\b(research|analyse|analyze|summarise|summarize|document|report|compare|deep.dive)\b')
_LOCAL_WORDS   = re.compile(r'\b(private|privately|offline|sensitive|confidential|secret)\b')
_SYSAGENT_WORDS = re.compile(
    # Unambiguous hardware state — always system
    r'\bbattery\b|\bcharging\b|\bbluetooth\s+devices?\b'
    # WiFi only when asking about state/availability (not "how does wifi work")
    r'|\bwifi\s+networks?\b|\bwireless\s+networks?\b'
    r'|\bavailable\s+(?:wifi|networks?|wireless)\b'
    r'|\bconnected\s+(?:to\s+)?(?:wifi|network)\b'
    # Disk/storage with explicit size intent
    r'|\bdisk\s+(?:space|usage|free)\b|\bfree\s+(?:space|disk)\b|\bstorage\s+(?:space|usage|free)\b'
    r'|\bhow\s+much\s+(?:ram|memory|disk|space|storage)\b'
    # Package management (always system action)
    r'|\b(?:install|uninstall|apt(?:-get)?)\s+\w+\b'
    r'|\bupdate\s+(?:the\s+)?(?:system|packages?|apt)\b'
    # Service / process management
    r'|\bsystemctl\b'
    r'|\brestart\s+\w+(?:service|daemon)\b'
    # Explicit current-state queries
    r'|\bwhat(?:\s+(?:is|are))?\s+(?:my|the|available)\s+(?:ip|networks?|processes?|services?|memory|ram)\b'
    r'|\b(?:check|show|list)\s+(?:my\s+)?(?:wifi|network|disk|memory|battery|services?|processes?|ip)\b'
    r'|\bmy\s+(?:ip|wifi|network|battery|disk|memory|ram)\b',
    re.I
)

# ── System context — real-time bash data injected before LLM call ─────────────
_SYSTEM_PROBES = [
    (re.compile(r'\bwifi\b|\bwireless\b|\bwlan\b|\bnetworks?\b', re.I),
     "nmcli device wifi list --rescan no 2>/dev/null | head -20"),
    (re.compile(r'\bip address\b|\bwhat.*ip\b|\bmy ip\b|\bconnected.*network\b', re.I),
     "ip addr show 2>/dev/null | grep -E 'state|inet '"),
    (re.compile(r'\bdisk\b|\bstorage\b|\bfree space\b|\bdf\b', re.I),
     "df -h 2>/dev/null"),
    (re.compile(r'\bmemory\b|\bram\b|\bswap\b', re.I),
     "free -h 2>/dev/null"),
    (re.compile(r'\bcpu\b|\bload\b|\bprocessor\b', re.I),
     "uptime && top -bn1 2>/dev/null | head -15"),
    (re.compile(r'\bbattery\b|\bcharging\b|\bpower\b', re.I),
     "cat /sys/class/power_supply/BAT*/capacity 2>/dev/null; cat /sys/class/power_supply/BAT*/status 2>/dev/null"),
    (re.compile(r'\bprocess\b|\bwhat.*running\b|\bapps.*running\b|\bps\b', re.I),
     "ps aux --sort=-%cpu 2>/dev/null | head -15"),
    (re.compile(r'\btemperature\b|\btemp\b|\bheat\b|\bthermal\b', re.I),
     "sensors 2>/dev/null | head -25"),
    (re.compile(r'\bservice\b|\bdaemon\b|\bsystemctl\b', re.I),
     "systemctl list-units --state=running --no-pager 2>/dev/null | head -20"),
    (re.compile(r'\bollama\b|\blocal model\b', re.I),
     "systemctl is-active ollama; curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -c \"import json,sys; d=json.load(sys.stdin); [print(m['name']) for m in d.get('models',[])]\" 2>/dev/null"),
    (re.compile(r'\buptime\b|\bhow long.*running\b|\bsince.*boot\b', re.I),
     "uptime 2>/dev/null"),
]

def _system_context(query: str) -> str:
    parts = []
    for pattern, cmd in _SYSTEM_PROBES:
        if pattern.search(query):
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                out = r.stdout.strip()
                if out:
                    label = cmd.split("2>/dev/null")[0].strip().split("|")[0].strip()
                    parts.append(f"$ {label}\n{out}")
            except Exception:
                pass
    return ("Live system state:\n" + "\n\n".join(parts)) if parts else ""

def route_query(raw: str) -> tuple[str, str, str]:
    q = raw.strip()

    # ── Explicit overrides ────────────────────────────────────────────────────
    if q.startswith("!!"):
        return ("model", "claude", q[2:].strip())
    if q.startswith("!g"):
        return ("model", "gemini", q[2:].strip())
    if q.startswith("!l"):
        return ("model", "local", q[2:].strip())
    if q.startswith("!s"):
        return ("agent", "sysagent", q[2:].strip() or q)
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
    if _SYSAGENT_WORDS.search(lower):
        return ("agent", "sysagent", q)

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

    # ── Default: Groq (fast, free, ~300 tok/s) ───────────────────────────────
    return ("model", "groq", q)


def _build_context(session_msgs: list[dict], memory: dict, query: str = "") -> str:
    rom     = load_context()
    hdd     = memory.get("hdd")
    ram     = memory.get("ram")
    profile = load_profile()

    parts = [
        f"You are Cascade, an AI assistant.\n"
        f"Be direct and concise. Today: {datetime.today():%A %d %B %Y}.\n"
        f"If you don't know something, say 'I don't have access to that' — never fabricate. Never say 'training data' or 'knowledge cutoff' — just answer directly or admit the gap plainly."
    ]
    if rom:     parts.append(f"Persistent context:\n{rom}")
    if profile: parts.append(f"User profile:\n{profile}")
    if ram:     parts.append(f"Semantic memory:\n{ram}")
    if hdd:     parts.append(f"Past conversations:\n{hdd}")
    sys_ctx = _system_context(query) if query else ""
    if sys_ctx: parts.append(sys_ctx)
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
        "[bold green]◆ CASCADE[/]   [dim]Groq · Gemini · Claude  ·  "
        "[bold]!![/] claude  ·  [bold]!g[/] gemini  ·  [bold]!s[/] sysagent  ·  "
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

            # ── Agent route (sysagent and future agents) ──────────────────────
            if route_type == "agent":
                from .agents import get_agent
                memory  = recall(clean_query or raw)
                context = _build_context(session_msgs, memory, clean_query or raw)
                try:
                    agent = get_agent(route_value)
                except ValueError:
                    route_type, route_value, clean_query = "model", "groq", raw
                else:
                    console.print(f"\n  [bold yellow]◆ {route_value.capitalize()}[/] [dim]— local, offline capable[/]\n")

                    def _on_tool(name, args):
                        cmd = args.get("command", args.get("path", "?"))
                        console.print(f"  [dim cyan][{name}][/] [dim]{cmd[:100]}[/]")

                    response, _ = agent.run(clean_query or raw, context, progress_cb=_on_tool)
                    console.print()
                    console.print(Panel(
                        Markdown(response),
                        title="[bold yellow]SysAgent[/]",
                        border_style="dim",
                        padding=(1, 2),
                    ))
                    console.print()
                    session_msgs.append({"role": "user",      "content": clean_query or raw})
                    session_msgs.append({"role": "assistant",  "content": response})
                    save(raw, response, route_value)
                    history.append((raw, response, route_value))
                    is_busy.clear()
                    continue

            if route_type == "skill":
                memory  = recall(clean_query or raw)
                context = _build_context(session_msgs, memory, clean_query or raw)
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

            memory        = recall(raw)
            context       = _build_context(session_msgs, memory, raw)
            role          = _ROLE_MAP.get(route_value, "general")
            registry      = _get_registry()
            provider_obj  = registry.get(route_value)
            actual_pid    = route_value if provider_obj else get_role_provider(role)
            style         = _PROVIDER_STYLE.get(actual_pid, "dim")
            label         = route_value.capitalize()
            stats         = TokenStats()

            # ── Streaming mode (API providers: Groq, Cerebras, OpenRouter) ──
            if provider_obj and hasattr(provider_obj, "stream"):
                console.print(f"\n  [{style}]{label}[/]\n")
                buf = []
                stream_failed = False
                try:
                    for token in provider_obj.stream(clean_query, context):
                        sys.stdout.write(token)
                        sys.stdout.flush()
                        buf.append(token)
                except Exception:
                    stream_failed = not buf

                if stream_failed:
                    # Remote unavailable — fall through role's provider chain to local
                    console.print("[dim]  ↳ remote unavailable — local[/]\n")
                    with Live(
                        Spinner("dots", text=" [dim]local thinking...[/]"),
                        console=console, refresh_per_second=12, transient=True
                    ):
                        response, stats = call_role_with_stats(role, clean_query, context)
                    tok_str = _fmt_tokens(stats)
                    console.print(Panel(
                        Markdown(response),
                        title="[bold yellow]Local[/]",
                        subtitle=f"[dim]{tok_str}[/]" if tok_str else None,
                        border_style="dim",
                        padding=(1, 2),
                    ))
                else:
                    response = "".join(buf)
                    console.print()

            # ── Batch mode (CLI providers: Claude, Gemini; Ollama) ──────────
            else:
                with Live(
                    Spinner("dots", text=f" [dim]{label} thinking...[/]"),
                    console=console, refresh_per_second=12, transient=True
                ):
                    if provider_obj:
                        response, stats = provider_obj.call_with_stats(clean_query, context)
                    else:
                        response, stats = call_role_with_stats(role, clean_query, context)

                tok_str = _fmt_tokens(stats)
                console.print(Panel(
                    Markdown(response),
                    title=f"[{style}]{label}[/]",
                    subtitle=f"[dim]{tok_str}[/]" if tok_str else None,
                    border_style="dim",
                    padding=(1, 2),
                ))

            session_total = session_total + stats
            ses_str       = _fmt_session(session_total)
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
