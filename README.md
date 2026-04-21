# Cascade

> A local-first AI coding agent that runs on your machine — and escalates to Claude only when it needs to.

---

## The Idea

Most AI coding tools send every request to the cloud. Cascade flips that:

- **90% of tasks** → handled by Qwen3:8b running locally via Ollama. Free, private, offline.
- **Hard tasks** → automatically escalated to Claude (via Claude Code CLI, no API key needed — just a Pro subscription).

You get privacy and zero cost for everyday work, with Claude as a silent expert on standby for the hard stuff.

---

## Architecture

```
User prompt
    │
    ▼
┌─────────────────────────────────────────┐
│           Cascade Agent Loop            │
│                                         │
│  ┌──────────┐  ┌──────────┐  ┌───────┐ │
│  │Programmer│→ │ Reviewer │→ │Tester │ │
│  └──────────┘  └──────────┘  └───────┘ │
│       │              │           │      │
│   Qwen3:8b       Qwen3:8b    Qwen3:8b  │
│  (local LLM)   (local LLM) (local LLM) │
│       │                                 │
│    uncertain / stuck?                   │
│       │                                 │
│       ▼                                 │
│  Claude Code CLI  ← Pro subscription   │
│  (escalation only)                      │
└─────────────────────────────────────────┘
    │
    ▼
.agent/worker-state.json   ← observable by any tool
```

### Three-Role Pipeline

| Role | Responsibility | Tools | Escalates when |
|------|---------------|-------|----------------|
| **Programmer** | Implements the task | bash, read, write, edit, glob, grep | Uncertain or stuck after N iterations |
| **Reviewer** | Reviews for bugs, correctness | read, glob, grep (read-only) | Uncertain about code quality |
| **Tester** | Runs and validates | bash, read, glob | Tests fail repeatedly |

### File-Based Observability

Every state transition writes atomically to `.agent/worker-state.json`:

```json
{
  "status": "processing",
  "task": "write a disk monitor script",
  "backend": "local",
  "iteration": 2,
  "elapsed_s": 14.3,
  "updated_at": "2026-04-21T10:32:11"
}
```

No HTTP server. No sockets. Any script can watch this file.

### Escalation Logic

Escalation happens automatically when:

1. Qwen3 expresses uncertainty (`"I don't know"`, `"I cannot"`, etc.)
2. A role exhausts its iteration budget
3. You force it with `--escalate`

When escalating, the full conversation context is passed to Claude — so it has everything Qwen3 had.

---

## Quickstart

**Requirements:**
- [Ollama](https://ollama.ai) running locally with `qwen3:8b`
- [Claude Code CLI](https://claude.ai/code) installed and authenticated

```bash
# Pull the model
ollama pull qwen3:8b

# Clone and run
git clone https://github.com/yourusername/cascade
cd cascade
python run.py "write a Python script that monitors disk usage and alerts at 90%"
```

---

## Usage

```bash
# Open interactive REPL (like the claude CLI)
cascade

# Single task — full agent pipeline
cascade "build a REST API client for the GitHub API"

# Skip testing (for non-executable tasks)
cascade "refactor utils.py to use dataclasses" --no-test

# Force Claude escalation
cascade "architect a distributed payment system" --escalate

# Agent + system dashboard
cascade status

# Start Telegram bot (requires TELEGRAM_TOKEN env var)
cascade bot

# List installed skills
cascade skills
```

### REPL shortcuts

| Input | Action |
|-------|--------|
| `!! <query>` | Force Claude (skip local) |
| `/graphify <text>` | Save to MemPalace knowledge graph |
| `history` | Show last 10 queries |
| `clear` | Clear history |
| `exit` | Quit |

---

## Performance

Response time depends entirely on your hardware:

| Hardware | Model | Avg response | Notes |
|----------|-------|-------------|-------|
| 16GB RAM (current) | Qwen3:8b | ~90s/call | Slower; escalation kicks in more often |
| 64GB RAM | Qwen3:32b | ~30s/call | Recommended sweet spot |
| 64GB RAM | Qwen3:72b Q4 | ~60s/call | Maximum local quality |

On 16GB RAM, complex tasks will frequently escalate to Claude — that's expected and by design. After a 64GB RAM upgrade, Qwen3:32b handles most tasks locally.

## Upgrading the Local Model

Cascade is model-agnostic. Change one line in `config.yml`:

```yaml
local_model: qwen3:8b      # current (16GB RAM)
# local_model: qwen3:32b   # after 64GB RAM upgrade — recommended
# local_model: qwen3:72b   # maximum quality, needs 64GB+
```

The escalation threshold naturally lowers as the local model gets smarter — fewer tasks reach Claude.

---

## Why This Matters

| Approach | Cost | Privacy | Quality |
|----------|------|---------|---------|
| Cloud-only (GPT-4, Claude API) | High | Low | High |
| Local-only (Ollama) | Free | High | Medium |
| **Cascade** | **Near-zero** | **High** | **High** |

The escalation layer means you never sacrifice quality. You just pay for it only when necessary.

---

## Project Structure

```
cascade/
├── cascade/
│   ├── agent.py          # coding agent loop — Programmer → Reviewer → Tester
│   ├── repl.py           # interactive REPL with MemPalace memory
│   ├── tools.py          # tool registry (bash, read, write, edit, grep, glob)
│   ├── roles.py          # role definitions + system prompts
│   ├── state.py          # state machine + atomic file writes
│   ├── llm.py            # Qwen3 (local) + Claude CLI (escalation)
│   ├── skills.py         # pluggable skills system
│   ├── status.py         # terminal dashboard
│   └── telegram_bot.py   # Telegram interface
├── skills/
│   └── graphify/         # /graphify skill — save to MemPalace KG
├── examples/
│   └── demo.sh
├── config.yml
├── run.py                # CLI entry point
└── .agent/
    └── worker-state.json # live agent state (gitignored)
```

---

## Inspired By

[claw-code](https://github.com/ultraworkers/claw-code) — open-source Rust reimplementation of Claude Code's agent harness. Cascade takes the same architectural patterns (state machines, file-based observability, role-based permissions) and applies them to a hybrid local/cloud setup.

---

## Roadmap

- [x] Interactive REPL (`cascade` command)
- [x] MemPalace shared memory — both models read/write same store
- [x] Skills system — `/skill <args>` in REPL
- [x] Telegram bot — send tasks from phone, results come back
- [x] `cascade status` dashboard
- [ ] `--watch` mode: stream `.agent/worker-state.json` to terminal live
- [ ] Persistent task history in SQLite
- [ ] Swap local model at runtime (`--model qwen3:32b`)
- [ ] Auto-start Telegram bot on login

---

## Author

Built by [Anil Vignesh](https://github.com/anilvignesh) — Senior PM in cross-border payments, building with AI.
