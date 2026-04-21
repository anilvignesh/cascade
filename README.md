# Cascade

A multi-model AI orchestration framework. Route tasks to the right model, share context and memory across all of them, and let them work in parallel — without API keys.

Cascade runs on CLI subscriptions (Gemini, Claude) and local models (Ollama). Add a model by editing one config file.

---

## How it works

```
cascade "research X and build Y"
              ↓
    Gemini (interpreter)
    plans the task, assigns agents
              ↓
    ┌─────────────────┬──────────────────┐
    │  researcher     │  analyst         │  ← parallel subprocesses
    │  (Gemini CLI)   │  (Gemini CLI)    │
    └─────────────────┴──────────────────┘
              ↓
    coder (Claude CLI) ← if implementation needed
              ↓
    Gemini synthesises → single final response
```

Every model call gets the same injected context:

| Layer | File | Role |
|---|---|---|
| ROM | `~/.cascade/context.md` | Persistent facts — you write this once |
| HDD | `~/.cascade/memory.md` | Past Q&A, keyword-searched automatically |
| RAM | MemPalace (optional) | Semantic graph memory, if installed |

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
```

Create your persistent context file:

```bash
mkdir -p ~/.cascade
nano ~/.cascade/context.md
# Write anything you want injected into every model call.
# Example: "I'm a backend engineer. Always use Python. Be concise."
```

---

## Usage

```bash
cascade                            # interactive REPL
cascade "do something"             # orchestrator — plans + runs agents + synthesises
cascade agent <name> "task"        # run a specific agent directly
cascade agents                     # list available agents
cascade learn                      # synthesise memory → update context.md
cascade skills                     # list installed skills
```

**REPL shortcuts:**
- `!! task` — force Claude
- `!g task` — force Gemini
- `/skillname args` — run a skill
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

  # Uncomment to enable local model (requires Ollama)
  # local:
  #   type: ollama
  #   model: llama3:8b
  #   url: http://localhost:11434/api/chat

roles:
  interpreter: gemini   # routes intent, orchestrates
  coder:       claude   # code, architecture, debugging
  researcher:  gemini   # research, analysis, drafting
  general:     gemini   # fallback

permissions:
  gemini:
    can_read_files:    false
    can_write_files:   false
    can_run_commands:  false
    can_access_memory: true
  claude:
    can_read_files:    true
    can_write_files:   true
    can_run_commands:  true
    can_access_memory: true
```

---

## Adding a model

Any model with a CLI or API can be added:

```yaml
# Local via Ollama
providers:
  local:
    type: ollama
    model: llama3:70b
    url: http://localhost:11434/api/chat

# API-based (optional)
  openai:
    type: api
    provider: openai
    model: gpt-4o
    api_key_env: OPENAI_API_KEY

# Assign to a role
roles:
  general: local
```

---

## Agents

Agents are autonomous workers with a think → act → observe loop. Define them in `config.yml`:

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

The orchestrator (`cascade "task"`) automatically plans which agents to use, runs independent steps in parallel, and synthesises the result.

Run an agent directly:

```bash
cascade agent researcher "how does SWIFT gpi work"
cascade agent coder "write a python script to parse CSV files"
```

---

## Learning

Cascade synthesises patterns from your interaction history and writes them into `context.md` as a `[LEARNED]` block. Your manually written content is never touched.

```bash
cascade learn
```

Schedule it nightly:

```bash
# crontab -e
0 2 * * * /path/to/cascade learn >> ~/.cascade/learn.log 2>&1
```

---

## Skills

Skills are pluggable modules in `cascade/skills/<name>/skill.py`. Each exposes a `DESCRIPTION` string and a `run(query, context)` function.

```bash
cascade skills        # list installed skills
/skillname args       # invoke from the REPL
```

---

## Project structure

```
cascade/
├── cascade/
│   ├── cli.py        # Entry point — all subcommands
│   ├── llm.py        # Provider registry (CLI / Ollama / API transports)
│   ├── agents.py     # Agent class + Orchestrator with parallel execution
│   ├── memory.py     # Three-layer memory (ROM / HDD / RAM)
│   ├── learn.py      # Memory synthesis → context.md
│   ├── repl.py       # Interactive REPL
│   ├── agent.py      # Programmer → Reviewer → Tester pipeline
│   ├── roles.py      # Role definitions
│   ├── tools.py      # Tool registry (bash, read, write, edit, glob, grep)
│   └── skills.py     # Skills loader
├── skills/           # Pluggable skill modules
├── config.yml        # All configuration
└── pyproject.toml
```

---

## Roadmap

- [ ] `cascade init` — auto-detect installed CLIs, generate config
- [ ] Web search plugin (Tavily)
- [ ] Browser automation plugin (browser-use)
- [ ] Document ingestion (markitdown)
- [ ] Sandboxed code execution (E2B)
- [ ] Advanced memory backends (mem0, Graphiti)
- [ ] `max_parallel` config option for rate limit control
