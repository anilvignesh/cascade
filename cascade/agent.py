"""
Core agent loop.
Programmer → Reviewer → Tester pipeline.
Each role runs locally (Qwen3). Escalates to Claude on uncertainty or failure.
"""

import json, re
from .state  import WorkerState, Status
from .roles  import PROGRAMMER, REVIEWER, TESTER, Role
from .tools  import execute
from .llm    import call_local, call_claude, should_escalate


TOOL_PATTERN = re.compile(
    r'<tool>\s*(\w+)\s*</tool>\s*<args>(.*?)</args>',
    re.DOTALL
)


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    calls = []
    for m in TOOL_PATTERN.finditer(text):
        name = m.group(1).strip()
        try:
            args = json.loads(m.group(2).strip())
        except json.JSONDecodeError:
            args = {"command": m.group(2).strip()}
        calls.append((name, args))
    return calls


def run_role(role: Role, task: str, state: WorkerState, context: str = "") -> tuple[str, bool]:
    """Run one role's loop. Returns (final_response, escalated)."""
    messages = [{"role": "system", "content": role.system_prompt}]
    if context:
        messages.append({"role": "user", "content": f"Context:\n{context}"})
    messages.append({"role": "user", "content": task})

    for i in range(role.max_iters):
        state.transition(Status.PROCESSING, backend="local", iteration=i)

        try:
            response = call_local(messages, max_tokens=1500)
        except Exception as e:
            response = f"local_error: {e}"

        # Check if escalation needed
        if should_escalate(response, i, role.max_iters):
            state.transition(Status.ESCALATING, backend="claude")
            print(f"\n  ↑ escalating to Claude ({role.name}, iter {i})")
            ctx = "\n".join(
                f"{m['role'].upper()}: {m['content']}" for m in messages
            )
            response = call_claude(task, context=ctx)
            return response, True

        # Execute any tool calls
        tool_calls = parse_tool_calls(response)
        if tool_calls:
            tool_results = []
            for name, args in tool_calls:
                out, err = execute(name, args, role.allowed_tools)
                tool_results.append(
                    f"[{name}] {'ERROR: ' + err if err else out[:2000]}"
                )
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user",      "content": "\n".join(tool_results)})
            continue

        # No tool calls — role is done
        messages.append({"role": "assistant", "content": response})
        return response, False

    # Exhausted iterations
    state.transition(Status.ESCALATING, backend="claude")
    print(f"\n  ↑ escalating to Claude (exhausted {role.name} iterations)")
    ctx = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    return call_claude(task, context=ctx), True


def run(task: str, skip_review: bool = False, skip_test: bool = False) -> dict:
    state = WorkerState()
    state.transition(Status.READY, task=task)

    results   = {}
    escalated = False
    context   = ""

    print(f"\n◆ CASCADE — {task[:80]}\n")

    # ── Programmer ──
    print("● Programmer (local)")
    code, esc = run_role(PROGRAMMER, task, state, context)
    results["programmer"] = code
    escalated = escalated or esc
    context = code
    print(f"  {'↑ claude' if esc else '✓ local'}")

    if not skip_review:
        # ── Reviewer ──
        print("● Reviewer (local)")
        review_task = f"Review this implementation:\n\n{code}"
        review, esc = run_role(REVIEWER, review_task, state, context)
        results["reviewer"] = review
        escalated = escalated or esc
        print(f"  {'↑ claude' if esc else '✓ local'}")

        if "CHANGES:" in review:
            print("● Programmer (revision)")
            revision_task = f"Original task: {task}\n\nReviewer feedback: {review}\n\nRevise accordingly."
            code, esc = run_role(PROGRAMMER, revision_task, state, context)
            results["revision"] = code
            escalated = escalated or esc
            context = code

    if not skip_test:
        # ── Tester ──
        print("● Tester (local)")
        test_task = f"Test this implementation:\n\n{context}"
        test_result, esc = run_role(TESTER, test_task, state, context)
        results["tester"] = test_result
        escalated = escalated or esc
        print(f"  {'↑ claude' if esc else '✓ local'}")

    state.transition(Status.COMPLETE)
    results["escalated"] = escalated
    return results
