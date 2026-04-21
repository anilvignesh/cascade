"""
General agent layer — any role can run as an autonomous agent.

Agent     — think → act → observe loop using any role from config.yml
Orchestrator — Gemini plans multi-agent tasks, dispatches, synthesises

Usage:
  cascade agent researcher "find UAE fintech regulations"
  cascade agent coder "build a REST API for payments"
  cascade "complex task"  → orchestrator decides
"""

import json, re, yaml
from dataclasses import dataclass, field
from pathlib import Path

from .llm   import call_role
from .tools import execute, REGISTRY

_CONFIG_PATH = Path(__file__).parent.parent / "config.yml"

_PATTERNS = [
    re.compile(r'<tool>\s*(\w+)\s*</tool>\s*<args>(.*?)</args>', re.DOTALL),
    re.compile(r'<function\s+name=["\'](\w+)["\'][^>]*>(.*?)</function>', re.DOTALL),
    re.compile(r'\{\s*"tool"\s*:\s*"(\w+)"\s*,\s*"args"\s*:\s*(\{.*?\})\s*\}', re.DOTALL),
]
_BASH_BLOCK = re.compile(r'```(?:bash|sh|shell)\n(.*?)```', re.DOTALL)


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    for pattern in _PATTERNS:
        calls = []
        for m in pattern.finditer(text):
            name = m.group(1).strip()
            if name not in REGISTRY:
                continue
            try:
                args = json.loads(m.group(2).strip())
            except json.JSONDecodeError:
                args = {"command": m.group(2).strip()}
            calls.append((name, args))
        if calls:
            return calls
    return [
        ("bash", {"command": m.group(1).strip()})
        for m in _BASH_BLOCK.finditer(text)
        if m.group(1).strip()
    ]


# ── Config ────────────────────────────────────────────────────────────────────

def _load_agent_configs() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text()).get("agents", {})


# ── Agent ─────────────────────────────────────────────────────────────────────

@dataclass
class Agent:
    name:          str
    role:          str
    tools:         list[str]
    max_iters:     int       = 8
    system_prompt: str       = ""

    def run(self, task: str, context: str = "") -> tuple[str, bool]:
        """
        ReAct loop: think → parse tools → execute → observe → repeat.
        Returns (response, escalated).
        """
        transcript: list[str] = []

        for i in range(self.max_iters):
            prompt   = self._build_prompt(task, transcript)
            full_ctx = f"{self.system_prompt}\n\n{context}".strip() if context else self.system_prompt

            try:
                response = call_role(self.role, prompt, full_ctx)
            except Exception as e:
                print(f"  [{self.name}] error: {e}, escalating to coder")
                return call_role("coder", task, full_ctx), True

            tool_calls = parse_tool_calls(response)

            if not tool_calls:
                return response, False

            results = self._execute_tools(tool_calls)
            transcript.append(f"THOUGHT:\n{response}")
            transcript.append(f"OBSERVATION:\n{results}")

        # Exhausted iterations — escalate to coder
        print(f"  [{self.name}] exhausted {self.max_iters} iterations, escalating")
        ctx = f"{self.system_prompt}\n\n{context}\n\n" + "\n\n".join(transcript)
        return call_role("coder", task, ctx), True

    def _build_prompt(self, task: str, transcript: list[str]) -> str:
        parts = [f"Task: {task}"]
        if transcript:
            parts.append("Progress so far:\n" + "\n\n".join(transcript))
            parts.append("Continue. Use tools if needed. When done, respond with your final answer only.")
        else:
            parts.append(
                "Think step by step. Use tools when needed.\n"
                "To call a tool use:\n"
                "<tool>bash</tool><args>{\"command\": \"echo hi\"}</args>\n"
                "<tool>read_file</tool><args>{\"path\": \"file.py\"}</args>\n"
                f"Available tools: {', '.join(self.tools) or 'none'}\n"
                "When fully done, respond with your final answer only — no tool calls."
            )
        return "\n\n".join(parts)

    def _execute_tools(self, calls: list[tuple[str, dict]]) -> str:
        results = []
        for name, args in calls:
            out, err = execute(name, args, self.tools)
            results.append(f"[{name}] {'ERROR: ' + err if err else out[:2000]}")
        return "\n".join(results)


# ── Registry ──────────────────────────────────────────────────────────────────

def get_agent(name: str) -> Agent:
    cfg = _load_agent_configs().get(name)
    if not cfg:
        raise ValueError(f"Agent '{name}' not defined in config.yml")
    return Agent(
        name          = name,
        role          = cfg.get("role", "general"),
        tools         = cfg.get("tools", []),
        max_iters     = cfg.get("max_iters", 8),
        system_prompt = cfg.get("system_prompt", f"You are a {name} agent. Be thorough and precise."),
    )


def list_agents() -> dict[str, str]:
    return {
        name: cfg.get("system_prompt", "")[:80]
        for name, cfg in _load_agent_configs().items()
    }


# ── Orchestrator ──────────────────────────────────────────────────────────────

_PLAN_PROMPT = """\
You are an orchestrator. Break the following task into steps for specialised agents.

Available agents:
{agents}

Task: {task}

Output a JSON plan — no explanation, no markdown, just the JSON:
{{"steps": [
  {{"agent": "researcher", "task": "specific sub-task description"}},
  {{"agent": "coder", "task": "specific sub-task description", "depends_on": 0}}
]}}

Rules:
- Use the most appropriate agent for each step
- "depends_on" is the index of a prior step whose output this step needs
- Keep steps focused — one clear goal per step
- Minimum steps needed, not maximum"""

_SYNTHESIS_PROMPT = """\
You orchestrated a multi-agent task. Synthesise the results into a single coherent response.

Original task: {task}

Agent outputs:
{outputs}

Write a clear, direct final response to the original task."""


class Orchestrator:
    def run(self, task: str, context: str = "") -> str:
        agents      = list_agents()
        agent_desc  = "\n".join(f"  {name}: {desc}" for name, desc in agents.items())

        # Step 1 — Plan
        print(f"\n◆ ORCHESTRATOR — planning: {task[:60]}\n")
        plan_response = call_role("interpreter",
                                   _PLAN_PROMPT.format(agents=agent_desc, task=task))

        steps = self._parse_plan(plan_response)
        if not steps:
            # Fallback: route directly as a single general task
            print("  [orchestrator] no valid plan, routing as general task")
            return call_role("general", task, context)

        # Step 2 — Execute steps, parallelising independent ones
        step_outputs: dict[int, str] = {}
        self._execute_steps(steps, step_outputs, task, context, len(steps))

        # Step 3 — Synthesise
        if len(step_outputs) == 1:
            return next(iter(step_outputs.values()))

        outputs_str = "\n\n".join(
            f"[Step {i+1} — {steps[i].get('agent')}]\n{out}"
            for i, out in step_outputs.items()
        )
        print(f"\n  [orchestrator] synthesising {len(steps)} outputs...")
        return call_role("researcher",
                          _SYNTHESIS_PROMPT.format(task=task, outputs=outputs_str))

    def _run_step(self, i: int, step: dict, step_outputs: dict,
                  task: str, context: str, total: int) -> tuple[int, str]:
        agent_name = step.get("agent", "researcher")
        sub_task   = step.get("task", task)
        depends_on = step.get("depends_on")

        dep_ctx  = f"Prior step output:\n{step_outputs[depends_on]}" \
                   if depends_on is not None and depends_on in step_outputs else ""
        full_ctx = "\n\n".join(filter(None, [context, dep_ctx]))

        print(f"  [{i+1}/{total}] {agent_name}: {sub_task[:60]}")
        try:
            output, _ = get_agent(agent_name).run(sub_task, full_ctx)
        except ValueError:
            output = call_role("general", sub_task, full_ctx)
        return i, output

    def _execute_steps(self, steps: list[dict], step_outputs: dict,
                       task: str, context: str, total: int):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        remaining = list(enumerate(steps))

        while remaining:
            # Find steps whose dependency is already resolved (or has none)
            ready = [
                (i, s) for i, s in remaining
                if s.get("depends_on") is None or s.get("depends_on") in step_outputs
            ]

            if not ready:
                # Shouldn't happen with a valid plan, but avoid infinite loop
                break

            if len(ready) == 1:
                i, step = ready[0]
                idx, output = self._run_step(i, step, step_outputs, task, context, total)
                step_outputs[idx] = output
            else:
                cfg          = yaml.safe_load(_CONFIG_PATH.read_text())
                max_parallel = cfg.get("orchestrator", {}).get("max_parallel", 3)
                workers      = min(len(ready), max_parallel)
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {
                        pool.submit(self._run_step, i, s, step_outputs, task, context, total): i
                        for i, s in ready
                    }
                    for future in as_completed(futures):
                        idx, output = future.result()
                        step_outputs[idx] = output

            remaining = [(i, s) for i, s in remaining if i not in step_outputs]

    def _parse_plan(self, response: str) -> list[dict]:
        try:
            m = re.search(r'\{.*\}', response, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return data.get("steps", [])
        except Exception:
            pass
        return []
