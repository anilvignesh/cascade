"""
LLM provider registry — config-driven, transport-agnostic.

Transports:
  cli    — subprocess call to a CLI binary (Gemini, Claude)
  ollama — local model via Ollama HTTP API
  api    — direct API access (optional, requires key)

Entry point: call_role(role, prompt, context)
"""

import json, subprocess, urllib.request, yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

CONFIG_PATH  = Path(__file__).parent.parent / "config.yml"
ENGLISH_RULE = "IMPORTANT: Always respond in English only."

_config:    dict = {}
_registry:  dict = {}


@dataclass
class TokenStats:
    input:    int = 0
    output:   int = 0
    total:    int = 0
    cost_usd: float = 0.0
    model:    str = ""

    def __add__(self, other: "TokenStats") -> "TokenStats":
        return TokenStats(
            input    = self.input    + other.input,
            output   = self.output   + other.output,
            total    = self.total    + other.total,
            cost_usd = self.cost_usd + other.cost_usd,
        )


# ── Config ────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    global _config
    if not _config:
        _config = yaml.safe_load(CONFIG_PATH.read_text())
    return _config


# ── Providers ─────────────────────────────────────────────────────────────────

class CLIProvider:
    def __init__(self, cfg: dict):
        self.bin         = str(Path(cfg["bin"]).expanduser())
        self.prompt_flag = cfg.get("prompt_flag")
        self.args        = cfg.get("args", [])

    def _build_cmd(self, full: str, extra_args: list[str] = []) -> list[str]:
        cmd = [self.bin]
        if self.prompt_flag:
            cmd += [self.prompt_flag, full]
        else:
            cmd.append(full)
        return cmd + self.args + extra_args

    def _clean(self, output: str) -> str:
        lines = [l for l in output.splitlines()
                 if not l.lower().startswith(("yolo mode", "✻ welcome"))]
        return "\n".join(lines).strip()

    def call(self, prompt: str, context: str = "", timeout: int = 120) -> str:
        full = f"{context}\n\n{prompt}".strip() if context else prompt
        proc = subprocess.run(
            self._build_cmd(full), capture_output=True, text=True, timeout=timeout
        )
        return self._clean(proc.stdout.strip() or proc.stderr.strip())

    def call_with_stats(self, prompt: str, context: str = "",
                        timeout: int = 120) -> tuple[str, TokenStats]:
        full = f"{context}\n\n{prompt}".strip() if context else prompt
        proc = subprocess.run(
            self._build_cmd(full, ["--output-format", "json"]),
            capture_output=True, text=True, timeout=timeout
        )
        raw = proc.stdout.strip() or proc.stderr.strip()
        try:
            data  = json.loads(raw)
            text  = data.get("response") or data.get("result", "")
            stats = self._parse_stats(data)
            return self._clean(text), stats
        except Exception:
            return self._clean(raw), TokenStats()

    def _parse_stats(self, data: dict) -> TokenStats:
        # Gemini CLI JSON: stats.models.<name>.tokens
        gemini_stats = data.get("stats", {}).get("models", {})
        if gemini_stats:
            inp = out = total = 0
            model = ""
            for name, mdata in gemini_stats.items():
                t = mdata.get("tokens", {})
                inp   += t.get("input", 0)
                out   += t.get("candidates", 0)
                total += t.get("total", 0)
                model  = name
            return TokenStats(input=inp, output=out, total=total, model=model)

        # Claude CLI JSON: usage.input_tokens / output_tokens
        usage = data.get("usage", {})
        if usage:
            inp  = usage.get("input_tokens", 0)
            out  = usage.get("output_tokens", 0)
            cost = data.get("total_cost_usd", 0.0)
            model = next(iter(data.get("modelUsage", {})), "claude")
            return TokenStats(input=inp, output=out, total=inp+out,
                              cost_usd=cost, model=model)

        return TokenStats()


class OllamaProvider:
    def __init__(self, cfg: dict):
        self.model = cfg["model"]
        self.url   = cfg.get("url", "http://localhost:11434/api/chat")

    def _messages(self, prompt: str, context: str) -> list[dict]:
        msgs = []
        if context:
            msgs.append({"role": "system", "content": f"{context}\n\n{ENGLISH_RULE}"})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def call(self, prompt: str, context: str = "", timeout: int = 300) -> str:
        payload = json.dumps({
            "model":   self.model,
            "messages": self._messages(prompt, context),
            "stream":  False,
            "options": {"num_predict": 2048, "temperature": 0.2},
        }).encode()
        req = urllib.request.Request(
            self.url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())["message"]["content"].strip()

    def stream(self, prompt: str, context: str = "", timeout: int = 300) -> Iterator[str]:
        payload = json.dumps({
            "model":   self.model,
            "messages": self._messages(prompt, context),
            "stream":  True,
            "options": {"num_predict": 1024, "temperature": 0.2},
        }).encode()
        req = urllib.request.Request(
            self.url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for line in resp:
                if line.strip():
                    chunk = json.loads(line.decode())
                    if not chunk.get("done") and "message" in chunk:
                        yield chunk["message"]["content"]


class APIProvider:
    """Stub for API-based providers (Anthropic, OpenAI, etc.)"""
    def __init__(self, cfg: dict):
        self.provider    = cfg["provider"]
        self.model       = cfg["model"]
        self.api_key_env = cfg.get("api_key_env")

    def call(self, prompt: str, context: str = "", timeout: int = 120) -> str:
        raise NotImplementedError(
            f"API provider '{self.provider}' not configured. "
            f"Set {self.api_key_env} and implement the transport."
        )


# ── Registry ──────────────────────────────────────────────────────────────────

def _get_registry() -> dict:
    global _registry
    if _registry:
        return _registry
    for name, pcfg in _load_config().get("providers", {}).items():
        t = pcfg.get("type")
        if   t == "cli":    _registry[name] = CLIProvider(pcfg)
        elif t == "ollama": _registry[name] = OllamaProvider(pcfg)
        elif t == "api":    _registry[name] = APIProvider(pcfg)
    return _registry


# ── Public API ────────────────────────────────────────────────────────────────

def call_role_with_stats(role: str, prompt: str,
                         context: str = "") -> tuple[str, TokenStats]:
    cfg         = _load_config()
    provider_id = cfg.get("roles", {}).get(role)
    if not provider_id:
        raise ValueError(f"No provider assigned to role '{role}'")
    provider = _get_registry().get(provider_id)
    if not provider:
        raise ValueError(f"Provider '{provider_id}' not found — check config.yml")
    if hasattr(provider, "call_with_stats"):
        return provider.call_with_stats(prompt, context)
    return provider.call(prompt, context), TokenStats()


def call_role(role: str, prompt: str, context: str = "") -> str:
    cfg         = _load_config()
    provider_id = cfg.get("roles", {}).get(role)
    if not provider_id:
        raise ValueError(f"No provider assigned to role '{role}'")
    provider = _get_registry().get(provider_id)
    if not provider:
        raise ValueError(f"Provider '{provider_id}' not found — check config.yml")
    return provider.call(prompt, context)


def get_role_provider(role: str) -> str:
    return _load_config().get("roles", {}).get(role, "gemini")


def has_permission(role: str, permission: str) -> bool:
    cfg         = _load_config()
    provider_id = cfg.get("roles", {}).get(role, "gemini")
    return cfg.get("permissions", {}).get(provider_id, {}).get(permission, False)


def should_escalate(response: str, iteration: int, max_iters: int) -> bool:
    uncertainty = [
        "i don't know", "i cannot", "i'm not sure", "i am not sure",
        "unable to", "i lack", "beyond my", "i don't have access",
    ]
    return any(p in response.lower() for p in uncertainty) or iteration >= max_iters - 1


# ── Legacy shims (used by agent.py / repl.py) ─────────────────────────────────

def call_claude(prompt: str, context: str = "") -> str:
    return call_role("coder", prompt, context)

def call_gemini(prompt: str, context: str = "") -> str:
    return call_role("researcher", prompt, context)
