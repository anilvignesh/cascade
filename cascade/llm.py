"""
LLM backends.
- Local:  Qwen3 via Ollama
- Escalate: Claude Code CLI (uses your Pro subscription, no API key needed)
"""

import json, subprocess, urllib.request
from pathlib import Path

OLLAMA_URL  = "http://localhost:11434/api/chat"
LOCAL_MODEL = "qwen3:8b"
CLAUDE_BIN  = str(Path.home() / ".local" / "bin" / "claude")

ENGLISH_RULE = "IMPORTANT: Always respond in English only."


def call_local(messages: list[dict], max_tokens: int = 2048, timeout: int = 300) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    chat_messages = [
        {"role": "system", "content": f"{system}\n\n{ENGLISH_RULE}".strip()},
        *[m for m in messages if m["role"] != "system"]
    ]
    payload = json.dumps({
        "model": LOCAL_MODEL,
        "messages": chat_messages,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["message"]["content"].strip()


def call_claude(prompt: str, context: str = "") -> str:
    full = f"{context}\n\n{prompt}".strip() if context else prompt
    proc = subprocess.run(
        [CLAUDE_BIN, "-p", full,
         "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
         "--dangerously-skip-permissions"],
        capture_output=True, text=True, timeout=300
    )
    return proc.stdout.strip() or proc.stderr.strip()


def should_escalate(response: str, iteration: int, max_iters: int) -> bool:
    uncertainty = [
        "i don't know", "i cannot", "i'm not sure", "i am not sure",
        "unable to", "i lack", "beyond my", "i don't have access",
    ]
    low_confidence = any(p in response.lower() for p in uncertainty)
    stuck = iteration >= max_iters - 1
    return low_confidence or stuck
