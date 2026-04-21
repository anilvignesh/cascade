# Architectural Proposal: Cascade Role-Based Orchestration

## Objective
Refactor Cascade from a fixed three-tier model (Local/Gemini/Claude) to a dynamic, role-based orchestration engine. This will allow flexible assignment of models (providers) to specific tasks (roles), optimizing for performance and hardware constraints.

## Problem Statement
The current 16GB RAM hardware causes the local Qwen3:8b model to respond slowly (~90s). Since it is hardcoded as the routing/interpretation layer, every user interaction experiences this delay.

## Proposed Architecture

### 1. Provider Abstraction
Introduce a base `LLMProvider` class in `llm.py`. Each model backend will implement this interface:
- **CLIProvider**: For models accessed via CLI (Gemini, Claude).
- **OllamaProvider**: For local models via Ollama API.

### 2. Registry Configuration
Model assignments move to `config.yml`.
```yaml
providers:
  ollama: { type: "ollama", model: "qwen3:8b" }
  gemini: { type: "cli", bin: "gemini", args: ["-p", "--yolo"] }
  claude: { type: "cli", bin: "claude", args: ["-p", "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep"] }

roles:
  interpreter: "gemini"  # Routing and intent classification
  reasoning:   "gemini"  # Research and analysis
  coder:       "claude"  # Implementation
  general:     "ollama"  # Fallback for simple chat
```

### 3. Unified Interface
The `llm.py` module will expose a `call_role(role, prompt, context)` function. This function:
1. Looks up the provider assigned to the role.
2. Injects shared context (MemPalace memory + session history).
3. Executes the provider call.

## Benefits
- **Performance**: Switch the `interpreter` role to Gemini to eliminate the 90s routing delay.
- **Flexibility**: Easily swap models (e.g., Gemini for coding or Qwen3:32b for reasoning) by editing the config.
- **Unified Brain**: Every model shares the same memory layer (MemPalace) and session context.

## Next Steps
1. Refactor `llm.py` to implement the Provider/Registry system.
2. Update `repl.py` and `agent.py` to use `call_role()`.
3. Update `config.yml` with the new provider/role structure.
