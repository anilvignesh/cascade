"""
cascade init — auto-detect installed CLIs, write a working config.yml.
"""

import shutil, yaml
from pathlib import Path

_CONFIG_PATH  = Path(__file__).parent.parent / "config.yml"
_CASCADE_DIR  = Path.home() / ".cascade"

_CLI_DEFAULTS = {
    "gemini": {
        "type":        "cli",
        "prompt_flag": "-p",
        "args":        ["--yolo"],
    },
    "claude": {
        "type":        "cli",
        "prompt_flag": "-p",
        "args":        ["--allowedTools",
                        "Bash,Read,Write,Edit,Glob,Grep",
                        "--dangerously-skip-permissions"],
    },
}

_ROLE_PRIORITY = ["gemini", "claude", "local"]

_DEFAULT_ROLES = {
    "interpreter": None,
    "researcher":  None,
    "general":     None,
    "coder":       "claude",
    "programmer":  "claude",
    "reviewer":    None,
    "tester":      None,
}

_DEFAULT_PERMISSIONS = {
    "gemini": {
        "can_read_files":    False,
        "can_write_files":   False,
        "can_run_commands":  False,
        "can_access_memory": True,
        "can_call_models":   False,
    },
    "claude": {
        "can_read_files":    True,
        "can_write_files":   True,
        "can_run_commands":  True,
        "can_access_memory": True,
        "can_call_models":   False,
    },
    "local": {
        "can_read_files":    False,
        "can_write_files":   False,
        "can_run_commands":  False,
        "can_access_memory": True,
        "can_call_models":   False,
    },
}


def _detect() -> dict:
    """Detect installed CLI binaries. Returns {name: bin_path}."""
    found = {}
    for name in ("gemini", "claude"):
        path = shutil.which(name)
        if path:
            found[name] = path
    # Ollama
    if shutil.which("ollama"):
        found["local"] = shutil.which("ollama")
    return found


def _pick_default(found: dict, preference: list[str]) -> str | None:
    for name in preference:
        if name in found:
            return name
    return None


def run():
    print("\n◆ CASCADE INIT\n")

    # 1 — Detect
    found = _detect()
    if not found:
        print("  No supported CLIs found.")
        print("  Install Gemini CLI, Claude CLI, or Ollama and run cascade init again.\n")
        return

    print("  Detected:")
    for name, path in found.items():
        print(f"    ✓ {name:<10} {path}")
    print()

    # 2 — Build providers config
    providers = {}
    for name, path in found.items():
        if name in _CLI_DEFAULTS:
            cfg = dict(_CLI_DEFAULTS[name])
            cfg["bin"] = path
            providers[name] = cfg
        elif name == "local":
            # Ollama — ask which model
            model = input("  Ollama detected. Which model? [gemma3] ").strip() or "gemma3"
            providers["local"] = {
                "type":  "ollama",
                "model": model,
                "url":   "http://localhost:11434/api/chat",
            }

    # 3 — Assign roles
    default_model = _pick_default(found, _ROLE_PRIORITY)
    roles = {}
    for role, forced in _DEFAULT_ROLES.items():
        if forced and forced in found:
            roles[role] = forced
        elif default_model:
            roles[role] = default_model

    # coder always prefers claude if available
    if "claude" in found:
        roles["coder"]      = "claude"
        roles["programmer"] = "claude"

    # 4 — Permissions (only for detected providers)
    permissions = {
        name: _DEFAULT_PERMISSIONS[name]
        for name in found
        if name in _DEFAULT_PERMISSIONS
    }

    # 5 — Agents (default set)
    agents = {
        "researcher": {
            "role":          "researcher",
            "tools":         ["bash", "read_file", "glob", "grep"],
            "max_iters":     6,
            "system_prompt": "You are a research agent. Gather information and summarise clearly.",
        },
        "coder": {
            "role":          "coder",
            "tools":         ["bash", "read_file", "write_file", "edit_file", "glob", "grep"],
            "max_iters":     10,
            "system_prompt": "You are a coding agent. Implement tasks fully. Output DONE when complete.",
        },
        "reviewer": {
            "role":          "researcher",
            "tools":         ["read_file", "glob", "grep"],
            "max_iters":     4,
            "system_prompt": "You are a reviewer. Output APPROVED or CHANGES: <feedback>.",
        },
        "analyst": {
            "role":          "researcher",
            "tools":         ["read_file", "bash"],
            "max_iters":     5,
            "system_prompt": "You are an analyst. Identify patterns and produce structured insights.",
        },
    }

    # 6 — Write config
    config = {
        "providers":   providers,
        "roles":       roles,
        "permissions": permissions,
        "agents":      agents,
        "memory": {
            "backend":      "file",
            "path":         "~/.cascade/memory.md",
            "context_file": "~/.cascade/context.md",
        },
    }

    _CONFIG_PATH.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))

    # 7 — Create ~/.cascade/
    _CASCADE_DIR.mkdir(exist_ok=True)
    ctx_file = _CASCADE_DIR / "context.md"
    mem_file = _CASCADE_DIR / "memory.md"
    if not ctx_file.exists():
        ctx_file.write_text(
            "# Persistent context\n"
            "# Write anything you want injected into every model call.\n"
            "# Example: I'm a backend engineer. Always use Python. Be concise.\n"
        )
    if not mem_file.exists():
        mem_file.touch()

    # 8 — Summary
    print(f"\n  Config written to {_CONFIG_PATH}")
    print(f"  Memory directory: {_CASCADE_DIR}")
    print(f"\n  Active providers: {', '.join(providers.keys())}")
    print(f"  Router:           {roles.get('interpreter', '—')}")
    print(f"  Coder:            {roles.get('coder', '—')}")
    print(f"\n  Edit {_CONFIG_PATH} to customise roles, add models, or adjust permissions.")
    print(f"  Edit {ctx_file} to add persistent context injected into every call.")
    print(f"\n  Run: cascade\n")
