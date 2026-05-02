"""
LLM provider registry — config-driven, transport-agnostic.

Transports:
  cli    — subprocess call to a CLI binary (Gemini, Claude)
  ollama — local model via Ollama HTTP API
  api    — OpenAI-compatible REST API (Groq, Cerebras, OpenRouter, etc.)

Entry point: call_role(role, prompt, context)

Roles support a priority list — providers are tried in order.
Remote providers (cli, api) are skipped when offline; local (ollama) always runs.
"""

import json, os, socket, subprocess, urllib.request, yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

CONFIG_PATH  = Path(__file__).parent.parent / "config.yml"
ENGLISH_RULE = "IMPORTANT: Always respond in English only. If you don't know something or lack current information, say so — never fabricate facts, statistics, or current events."

_config:   dict = {}
_registry: dict = {}


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


# ── Connectivity ──────────────────────────────────────────────────────────────

def is_online(host: str = "8.8.8.8", port: int = 53, timeout: int = 2) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


# ── Config ────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    global _config
    if not _config:
        _config = yaml.safe_load(CONFIG_PATH.read_text())
    return _config


def _role_providers(role: str) -> list[str]:
    val = _load_config().get("roles", {}).get(role)
    if val is None:
        return []
    return val if isinstance(val, list) else [val]


# ── Providers ─────────────────────────────────────────────────────────────────

class CLIProvider:
    offline_capable = False

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

    def call(self, prompt: str, context: str = "", timeout: int = 600) -> str:
        full = f"{context}\n\n{prompt}".strip() if context else prompt
        proc = subprocess.run(
            self._build_cmd(full), capture_output=True, text=True, timeout=timeout
        )
        return self._clean(proc.stdout.strip() or proc.stderr.strip())

    def call_with_stats(self, prompt: str, context: str = "",
                        timeout: int = 600) -> tuple[str, TokenStats]:
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
    offline_capable = True

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
            "model":    self.model,
            "messages": self._messages(prompt, context),
            "stream":   False,
            "options":  {"num_predict": 2048, "temperature": 0.2},
        }).encode()
        req = urllib.request.Request(
            self.url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())["message"]["content"].strip()

    def stream(self, prompt: str, context: str = "", timeout: int = 300) -> Iterator[str]:
        payload = json.dumps({
            "model":    self.model,
            "messages": self._messages(prompt, context),
            "stream":   True,
            "options":  {"num_predict": 1024, "temperature": 0.2},
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
    """OpenAI-compatible REST API — covers Groq, Cerebras, OpenRouter, etc."""
    offline_capable = False

    def __init__(self, cfg: dict):
        self.base_url    = cfg["base_url"].rstrip("/")
        self.model       = cfg["model"]
        self.api_key_env = cfg.get("api_key_env", "")

    def _key(self) -> str:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise ValueError(f"API key env var '{self.api_key_env}' is not set")
        return key

    def _messages(self, prompt: str, context: str) -> list[dict]:
        msgs = []
        if context:
            msgs.append({"role": "system", "content": f"{context}\n\n{ENGLISH_RULE}"})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def _request(self, prompt: str, context: str, timeout: int) -> dict:
        payload = json.dumps({
            "model":    self.model,
            "messages": self._messages(prompt, context),
            "stream":   False,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {self._key()}",
                "User-Agent":    "cascade/1.0",
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def call(self, prompt: str, context: str = "", timeout: int = 60) -> str:
        data = self._request(prompt, context, timeout)
        return data["choices"][0]["message"]["content"].strip()

    def call_with_stats(self, prompt: str, context: str = "",
                        timeout: int = 60) -> tuple[str, TokenStats]:
        data  = self._request(prompt, context, timeout)
        text  = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})
        stats = TokenStats(
            input  = usage.get("prompt_tokens", 0),
            output = usage.get("completion_tokens", 0),
            total  = usage.get("total_tokens", 0),
            model  = self.model,
        )
        return text, stats

    def stream(self, prompt: str, context: str = "", timeout: int = 60) -> Iterator[str]:
        payload = json.dumps({
            "model":    self.model,
            "messages": self._messages(prompt, context),
            "stream":   True,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {self._key()}",
                "User-Agent":    "cascade/1.0",
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode().strip()
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    choices = chunk.get("choices", [])
                    if choices:
                        content = choices[0].get("delta", {}).get("content")
                        if content:
                            yield content
                except Exception:
                    pass


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

def _try_providers(role: str, prompt: str,
                   context: str, with_stats: bool) -> tuple[str, TokenStats]:
    ids = _role_providers(role)
    if not ids:
        raise ValueError(f"No provider assigned to role '{role}'")

    online    = None  # lazy — only check once, only if needed
    last_err  = Exception(f"No usable provider for role '{role}'")
    registry  = _get_registry()

    for pid in ids:
        provider = registry.get(pid)
        if not provider:
            continue
        if not provider.offline_capable:
            if online is None:
                online = is_online()
            if not online:
                continue
        try:
            if with_stats and hasattr(provider, "call_with_stats"):
                return provider.call_with_stats(prompt, context)
            return provider.call(prompt, context), TokenStats()
        except Exception as e:
            last_err = e
            continue

    raise last_err


def call_role(role: str, prompt: str, context: str = "") -> str:
    text, _ = _try_providers(role, prompt, context, with_stats=False)
    return text


def call_role_with_stats(role: str, prompt: str,
                         context: str = "") -> tuple[str, TokenStats]:
    return _try_providers(role, prompt, context, with_stats=True)


def get_role_provider(role: str) -> str:
    ids = _role_providers(role)
    return ids[0] if ids else "gemini"


def has_permission(role: str, permission: str) -> bool:
    cfg        = _load_config()
    provider_id = get_role_provider(role)
    return cfg.get("permissions", {}).get(provider_id, {}).get(permission, False)


def should_escalate(response: str, iteration: int, max_iters: int) -> bool:
    uncertainty = [
        "i don't know", "i cannot", "i'm not sure", "i am not sure",
        "unable to", "i lack", "beyond my", "i don't have access",
    ]
    return any(p in response.lower() for p in uncertainty) or iteration >= max_iters - 1


# ── Legacy shims ──────────────────────────────────────────────────────────────

def call_claude(prompt: str, context: str = "") -> str:
    return call_role("coder", prompt, context)

def call_gemini(prompt: str, context: str = "") -> str:
    return call_role("researcher", prompt, context)
