# Cascade

> A local-first AI assistant and coding agent — Qwen3 for speed, Gemini for research, Claude for hard coding.

---

## What It Is

Cascade is a personal AI system built around three models in a smart routing layer:

- **Qwen3:8b** (local via Ollama) — free, private, instant for simple queries
- **Gemini** (Google CLI, OAuth) — research, analysis, news, job briefings, conversation
- **Claude** (Claude Code CLI, Pro sub) — complex coding, architecture, implementation

Every message is automatically routed to the right model. You can override with `!!` (Claude) or `!g` (Gemini).

---

## Architecture

```
User input (REPL or Telegram)
       │
       ▼  Qwen3 classifier (max_tokens=10, ~5s)
       ├── local  → Qwen3 streams answer
       ├── gemini → Gemini answers
       └── claude → Claude Code CLI answers
              │
              ↓ (on uncertainty or iteration exhaustion)
         escalation to Claude
```

All responses are saved to MemPalace — shared memory across REPL, Telegram, and the agent pipeline.

---

## Interfaces

### Terminal REPL
```bash
cascade
```
Streaming output from Qwen3. Gemini and Claude responses print after completion.

| Input | Action |
|-------|--------|
| `!! <query>` | Force Claude |
| `!g <query>` | Force Gemini |
| `/skill <args>` | Run a skill |
| `history` | Last 10 queries |
| `clear` | Clear session |
| `exit` | Quit |

### Single task (agent pipeline)
```bash
cascade "build a rate limiter in Python"
cascade "refactor utils.py to use dataclasses" --no-test
cascade "architect a multi-tenant payment system" --escalate
```
Runs Programmer → Reviewer → Tester pipeline. Escalates to Claude on uncertainty.

### Telegram bot
```bash
cascade bot
```
Full coordinator — handles text, voice, documents, photos. Same routing logic as REPL.
System tasks (install, update, rm) require **"jarvis do it"** to confirm before execution.

### Background watcher (cron)
Monitors jobs and news every 4 hours. Sends Telegram alerts for high-fit jobs and fintech news.

### Daily brief
```bash
cascade brief
```
Morning briefing sent to Telegram — news + job digest.

---

## Skills

| Skill | Backend | What it does |
|-------|---------|-------------|
| `/news` | Gemini | Curated fintech briefing — picks what matters to you, explains why |
| `/jobs` | Gemini | Analyses high-fit jobs — what to apply for, what to highlight, what gaps exist |
| `/email inbox` | Gemini + Claude | Summarises inbox; reads full thread before drafting replies |
| `/email reply <subject>: <intent>` | Claude | Reads full thread context, drafts in your voice |
| `/calendar today/week/free/add` | Claude | Google Calendar read and create |
| `/browse <url or query>` | — | Fetch URL or web search |
| `/match` | Claude | Match resume against cached job listings |
| `/remind <text>` | — | Natural language reminders |
| `/system` | Qwen3 | RAM, disk, Ollama, Gemini, MemPalace, Cascade status |
| `/plan trip <destination>` | Gemini | Visa, areas, itinerary, budget |
| `/plan research <company/topic>` | Gemini | Deep brief with fresh web data |
| `/plan interview <company> [role]` | Gemini | Fit analysis, likely questions, talking points |
| `/plan meeting <person/topic>` | Gemini | Agenda, context, what to push for |
| `/graphify <text>` | — | Save to MemPalace knowledge graph |

---

## Agent Pipeline

Used for coding tasks (`cascade "task"`):

| Role | Tools | Max iterations | Escalates when |
|------|-------|---------------|----------------|
| Programmer | bash, read, write, edit, glob, grep | 8 | Uncertain or stuck |
| Reviewer | read, glob, grep (read-only) | 3 | Uncertain about quality |
| Tester | bash, read, glob | 4 | Tests fail repeatedly |

Tool call formats supported: XML (`<tool>`), function XML (`<function>`), JSON object, markdown bash blocks.

---

## Memory

All exchanges (REPL, Telegram, skills) are saved to MemPalace at `~/.mempalace/palace`.
Sessions from `~/.claude/projects/` are mined into MemPalace on every Claude Code exit.

Both Cascade and Claude Code share the same memory store — context flows between them.

---

## Configuration

**`config.yml`** — model and escalation settings:
```yaml
local_model: qwen3:8b      # swap to qwen3:32b after 64GB RAM upgrade
```

**`~/.cascade.env`** — secrets:
```
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
```

**`~/.gemini/settings.json`** — Gemini OAuth (auto-configured on first `gemini` login).

---

## Setup

**Requirements:**
- [Ollama](https://ollama.ai) with `qwen3:8b` pulled
- [Claude Code CLI](https://claude.ai/code) authenticated (Pro subscription)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) authenticated (Google account)

```bash
# Clone
git clone https://github.com/anilvignesh/cascade
cd cascade
pip install -e .

# Pull local model
ollama pull qwen3:8b

# Authenticate Gemini (one-time)
gemini

# Run
cascade
```

---

## Hardware

Current: AMD Ryzen 5 7530U, 16GB DDR4 3200MHz, 476GB NVMe.

At 16GB, Qwen3:8b runs in ~90s/call and Claude escalation happens often. After upgrading to 64GB RAM, swap to `qwen3:32b` in `config.yml` — response time drops to ~30s and most tasks stay local.

---

## Project Structure

```
cascade/
├── cascade/
│   ├── llm.py            # Three backends: call_local, call_gemini, call_claude
│   ├── repl.py           # Interactive REPL with streaming Qwen3
│   ├── agent.py          # Coding agent loop — Programmer → Reviewer → Tester
│   ├── telegram_bot.py   # Telegram coordinator — text, voice, docs, photos
│   ├── tools.py          # Tool registry (bash, read, write, edit, grep, glob)
│   ├── roles.py          # Role definitions + system prompts
│   ├── skills.py         # Skills loader
│   ├── watcher.py        # Background job + news watcher
│   ├── brief.py          # Daily brief generator
│   └── state.py          # Agent state machine
├── skills/
│   ├── news/             # Gemini-powered fintech briefing
│   ├── jobs/             # Gemini job fit analysis
│   ├── email/            # Claude email agent (full thread context)
│   ├── calendar/         # Google Calendar
│   ├── browse/           # Web fetch + search
│   ├── match/            # Resume-job matching
│   ├── remind/           # Reminders
│   ├── system/           # Laptop health
│   └── graphify/         # MemPalace KG
├── config.yml
├── run.py
└── .agent/
    └── worker-state.json # Live agent state
```

---

## Author

Built by [Anil Vignesh](https://github.com/anilvignesh) — Senior PM in cross-border payments.
