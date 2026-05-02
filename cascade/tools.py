"""
Tool registry — what the agent can actually do.
Each tool returns (output: str, error: str | None).
"""

import subprocess, json
from pathlib import Path
from glob import glob as _glob


REGISTRY = {}

def tool(name):
    def decorator(fn):
        REGISTRY[name] = fn
        return fn
    return decorator


@tool("bash")
def bash(command: str, timeout: int = 300) -> tuple[str, str | None]:
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        out = r.stdout + (r.stderr if r.returncode != 0 else "")
        return out.strip(), None if r.returncode == 0 else f"exit {r.returncode}"
    except subprocess.TimeoutExpired:
        return "", "timeout"
    except Exception as e:
        return "", str(e)


@tool("read_file")
def read_file(path: str) -> tuple[str, str | None]:
    try:
        return Path(path).read_text(), None
    except Exception as e:
        return "", str(e)


@tool("write_file")
def write_file(path: str, content: str) -> tuple[str, str | None]:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Written: {path}", None
    except Exception as e:
        return "", str(e)


@tool("edit_file")
def edit_file(path: str, old: str, new: str) -> tuple[str, str | None]:
    try:
        p = Path(path)
        text = p.read_text()
        if old not in text:
            return "", f"String not found in {path}"
        p.write_text(text.replace(old, new, 1))
        return f"Edited: {path}", None
    except Exception as e:
        return "", str(e)


@tool("glob")
def glob(pattern: str) -> tuple[str, str | None]:
    try:
        matches = _glob(pattern, recursive=True)
        return "\n".join(matches) if matches else "(no matches)", None
    except Exception as e:
        return "", str(e)


@tool("grep")
def grep(pattern: str, path: str = ".", file_glob: str = "*") -> tuple[str, str | None]:
    try:
        r = subprocess.run(
            ["grep", "-r", "-n", "--include", file_glob, pattern, path],
            capture_output=True, text=True, timeout=15
        )
        return r.stdout.strip() or "(no matches)", None
    except Exception as e:
        return "", str(e)


@tool("search")
def search(query: str) -> tuple[str, str | None]:
    from .llm import call_role
    try:
        prompt = f"RESEARCH TASK: {query}\n\nFind latest data, verify facts, and provide a structured summary."
        res = call_role("researcher", prompt)
        return res.strip(), None
    except Exception as e:
        return "", str(e)


def execute(name: str, args: dict, allowed: list[str]) -> tuple[str, str | None]:
    if name not in allowed:
        return "", f"Tool '{name}' not permitted in this role"
    if name not in REGISTRY:
        return "", f"Unknown tool: {name}"
    return REGISTRY[name](**args)
