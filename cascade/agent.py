"""
Core agent loop — Programmer → Reviewer → Tester pipeline.
Each role calls the model assigned to it in config.yml.
Escalates to the 'coder' role (Claude) on uncertainty or failure.
"""

import json, re
from .state import WorkerState, Status
from .roles import PROGRAMMER, REVIEWER, TESTER, Role
from .tools import execute, REGISTRY
from .llm   import call_role, should_escalate


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


def _build_context(role: Role, task: str, transcript: list[str], initial_context: str) -> str:
    parts = [role.system_prompt]
    if initial_context:
        parts.append(f"Context:\n{initial_context}")
    parts.append(f"Task:\n{task}")
    if transcript:
        parts.append("Conversation so far:\n" + "\n".join(transcript))
    return "\n\n".join(parts)


def run_role(role: Role, task: str, state: WorkerState, context: str = "") -> tuple[str, bool]:
    """Run one role's loop. Returns (final_response, escalated)."""
    transcript: list[str] = []

    for i in range(role.max_iters):
        state.transition(Status.PROCESSING, backend=role.name, iteration=i)

        ctx = _build_context(role, task, transcript, context)
        prompt = transcript[-1] if transcript else task

        try:
            response = call_role(role.name, prompt, ctx)
        except Exception as e:
            state.transition(Status.ESCALATING, backend="claude")
            print(f"\n  ↑ escalating to Claude ({role.name}, error: {e})")
            return call_role("coder", task, ctx), True

        if should_escalate(response, i, role.max_iters):
            state.transition(Status.ESCALATING, backend="claude")
            print(f"\n  ↑ escalating to Claude ({role.name}, iter {i})")
            return call_role("coder", task, ctx), True

        tool_calls = parse_tool_calls(response)
        if tool_calls:
            tool_results = []
            for name, args in tool_calls:
                out, err = execute(name, args, role.allowed_tools)
                tool_results.append(f"[{name}] {'ERROR: ' + err if err else out[:2000]}")
            transcript.append(f"ASSISTANT: {response}")
            transcript.append(f"TOOL RESULTS: {chr(10).join(tool_results)}")
            continue

        transcript.append(f"ASSISTANT: {response}")
        return response, False

    state.transition(Status.ESCALATING, backend="claude")
    print(f"\n  ↑ escalating to Claude (exhausted {role.name} iterations)")
    ctx = _build_context(role, task, transcript, context)
    return call_role("coder", task, ctx), True


def run(task: str, skip_review: bool = False, skip_test: bool = False,
        force_escalate: bool = False) -> dict:
    state = WorkerState()
    state.transition(Status.READY, task=task)

    results   = {}
    escalated = False
    context   = ""

    print(f"\n◆ CASCADE — {task[:80]}\n")

    if force_escalate:
        print("● Claude (forced)")
        code = call_role("coder", task)
        results["programmer"] = code
        results["escalated"]  = True
        state.transition(Status.COMPLETE)
        return results

    print("● Programmer")
    code, esc = run_role(PROGRAMMER, task, state, context)
    results["programmer"] = code
    escalated = escalated or esc
    context   = code
    print(f"  {'↑ claude' if esc else '✓ done'}")

    if not skip_review:
        print("● Reviewer")
        review, esc = run_role(REVIEWER, f"Review this implementation:\n\n{code}", state, context)
        results["reviewer"] = review
        escalated = escalated or esc
        print(f"  {'↑ claude' if esc else '✓ done'}")

        if "CHANGES:" in review:
            print("● Programmer (revision)")
            revision_task = f"Original task: {task}\n\nReviewer feedback: {review}\n\nRevise accordingly."
            code, esc = run_role(PROGRAMMER, revision_task, state, context)
            results["revision"] = code
            escalated = escalated or esc
            context   = code

    if not skip_test:
        print("● Tester")
        test_task = (
            f"Original task: {task}\n\n"
            f"Implementation:\n\n{context}\n\n"
            f"Run it, verify it works, report PASS or FAIL."
        )
        test_result, esc = run_role(TESTER, test_task, state, context)
        results["tester"]  = test_result
        escalated = escalated or esc
        print(f"  {'↑ claude' if esc else '✓ done'}")

    state.transition(Status.COMPLETE)
    results["escalated"] = escalated
    return results
