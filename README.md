# Cascade

A multi-model AI orchestration framework for your terminal. Route tasks to the right model, share memory across all of them, and let agents work in parallel — without API keys.

Cascade runs on CLI subscriptions (Gemini CLI, Claude Code) and local models (Ollama). Adding a new model is one edit to `config.yml`.

---

## The idea

Most AI frameworks require API keys and charge per token. Cascade uses the CLI tools you already pay for — Gemini CLI (Google One) and Claude Code (Anthropic subscription) — and wraps them in a single interface with shared memory.

When you give it a task, a reasoning model (Gemini) plans how to break it down, assigns the right agent to each part, runs independent parts in parallel, and synthesises a final response. Add a new model, assign it to a role, and the orchestrator uses it automatically.

```
cascade "research X and build Y"
              ↓
    Gemini (interpreter)
    plans the task, assigns agents
              ↓
    ┌─────────────────┬──────────────────┐
    │  researcher     │  analyst         │  ← run in parallel
    │  (Gemini CLI)   │  (Gemini CLI)    │
    └─────────────────┴──────────────────┘
              ↓
    coder (Claude CLI) ← if implementation needed
              ↓
    Gemini synthesises → final response
```

---

## Memory

Every model call gets the same injected context:

| Layer | File | Role |
|---|---|---|
| ROM | `~/.cascade/context.md` | Persistent facts — you write this once |
| HDD | `~/.cascade/memory.md` | Past Q&A, keyword-searched on each call |
| RAM | MemPalace (optional) | Semantic graph memory, if installed |

Run `cascade learn` to synthesise patterns from your history into `context.md` automatically.

---

## Prerequisites

At least one of:

| Model | Requirement |
|---|---|
| **Gemini CLI** | [Install](https://github.com/google-gemini/gemini-cli) — Google account or Google One subscription |
| **Claude CLI** | [Install](https://claude.ai/code) — Anthropic subscription |
| **Ollama** | [Install](https://ollama.com) — local hardware (8GB+ RAM recommended) |

Python 3.10+

---

## Setup

```bash
git clone https://github.com/anilvignesh/cascade.git
cd cascade
pip install -e .
cascade init        # auto-detects installed CLIs, writes config.yml
```

Or manually create your context file:

```bash
mkdir -p ~/.cascade
echo "I'm a backend engineer. Always use Python. Be concise." > ~/.cascade/context.md
```

---

## Usage

```bash
cascade                            # interactive REPL
cascade "do something"             # orchestrator — plans, runs agents, synthesises
cascade agent <name> "task"        # run a specific agent directly
cascade agents                     # list available agents
cascade skills                     # list installed skills
cascade learn                      # synthesise memory → update context.md
cascade status                     # provider health + last agent run
```

**REPL shortcuts:**
- `!! task` — force Claude
- `!g task` — force Gemini
- `/skillname args` — run a skill (e.g. `/search SWIFT gpi`)
- `history` — show recent queries
- `clear` — reset session context

---

## Configuration

Everything lives in `config.yml`:

```yaml
providers:
  gemini:
    type: cli
    bin: ~/.local/bin/gemini
    prompt_flag: "-p"
    args: ["--yolo"]

  claude:
    type: cli
    bin: ~/.local/bin/claude
    prompt_flag: "-p"
    args: ["--allowedTools", "Bash,Read,Write,Edit,Glob,Grep", "--dangerously-skip-permissions"]

  # Uncomment to add a local model via Ollama
  # local:
  #   type: ollama
  #   model: llama3:8b
  #   url: http://localhost:11434/api/chat

roles:
  interpreter: gemini   # routes intent, orchestrates
  coder:       claude   # code, architecture, debugging
  researcher:  gemini   # research, analysis, drafting
  general:     gemini   # fallback
```

Assign any role to any model. The orchestrator reads this at runtime.

---

## Agents

Agents are named workers: a model role + a purpose + a set of tools. Define them in `config.yml`:

```yaml
agents:
  researcher:
    role: researcher
    tools: [bash, read_file, glob, grep]
    max_iters: 6
    system_prompt: "You are a research agent. Gather and summarise information clearly."

  coder:
    role: coder
    tools: [bash, read_file, write_file, edit_file, glob, grep]
    max_iters: 10
    system_prompt: "You are a coding agent. Implement tasks fully. Output DONE when complete."
```

The orchestrator (`cascade "task"`) plans which agents to use, runs independent steps in parallel, and synthesises the result. Run an agent directly:

```bash
cascade agent researcher "how does SWIFT gpi work"
cascade agent coder "write a Python script to parse CSV files"
```

---

## Skills

Skills are pluggable modules in `skills/<name>/skill.py`. Each exposes a `DESCRIPTION` string and a `run(query, context)` function. Call them from the REPL with `/skillname`.

Built-in skills:

| Skill | What it does |
|---|---|
| `/search` | Web search — Tavily API or DuckDuckGo fallback |
| `/ingest` | Convert any file or URL to markdown (PDF, Word, Excel, HTML, images) |

---

## Learning

Cascade synthesises patterns from your interaction history and writes them into `context.md` as a `[LEARNED]` block. Your manually written content is never modified.

```bash
cascade learn

# or schedule it nightly
# crontab -e
# 0 2 * * * /path/to/cascade learn >> ~/.cascade/learn.log 2>&1
```

---

## Project structure

```
cascade/
├── cascade/
│   ├── cli.py          # Entry point — all subcommands
│   ├── llm.py          # Provider registry (CLI / Ollama / API transports)
│   ├── agents.py       # Agent + Orchestrator (parallel execution)
│   ├── memory.py       # Three-layer memory (ROM / HDD / RAM)
│   ├── learn.py        # Memory synthesis → context.md
│   ├── repl.py         # Interactive REPL with Rich UI
│   ├── init_cmd.py     # cascade init — auto-detect CLIs, write config
│   ├── tools.py        # Tool registry (bash, read, write, edit, glob, grep)
│   └── skills.py       # Skills loader
├── skills/             # Pluggable skill modules
│   ├── search/         # Web search (Tavily + DDG)
│   └── ingest/         # Document ingestion (markitdown)
├── config.yml          # All configuration
└── pyproject.toml
```

---

## Roadmap

- [x] Config-driven provider registry (CLI / Ollama / API)
- [x] Role-based model routing
- [x] Three-layer memory (ROM / HDD / RAM)
- [x] Agent + Orchestrator with parallel execution
- [x] `cascade init` — auto-detect installed CLIs
- [x] Web search skill (Tavily + DuckDuckGo fallback)
- [x] Document ingestion skill (markitdown)
- [x] `max_parallel` for rate limit control
- [x] Nightly learning synthesis (`cascade learn`)
- [ ] More models — test with local Ollama models
- [ ] Browser automation skill (Playwright)
- [ ] Sandboxed code execution
