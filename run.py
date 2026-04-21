#!/usr/bin/env python3
"""
Cascade — local-first AI with Claude escalation + MemPalace memory.

  cascade               → interactive REPL
  cascade "do a task"   → single task, full agent pipeline
  cascade status        → agent + system dashboard
  cascade bot           → start Telegram bot
  cascade skills        → list available skills
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    args = sys.argv[1:]

    # ── Subcommands ──
    if not args or args[0] == "repl":
        from cascade.repl import run
        run()
        return

    if args[0] == "status":
        from cascade.status import show
        show()
        return

    if args[0] == "bot":
        from cascade.telegram_bot import run
        run()
        return

    if args[0] == "skills":
        from cascade.skills import list_skills
        skills = list_skills()
        if skills:
            print("\nAvailable skills:")
            for name, desc in skills.items():
                print(f"  /{name:<16} {desc}")
        else:
            print("No skills installed. Add them to ~/cascade/skills/")
        print()
        return

    # ── Agent pipeline (task as argument) ──
    import argparse, json
    from cascade.agent import run as agent_run

    parser = argparse.ArgumentParser(
        description="Cascade — local-first AI coding agent",
        prog="cascade",
    )
    parser.add_argument("task",         help="What to build or fix")
    parser.add_argument("--no-review",  action="store_true", help="Skip reviewer")
    parser.add_argument("--no-test",    action="store_true", help="Skip tester")
    parser.add_argument("--escalate",   action="store_true", help="Force Claude")
    parser.add_argument("--json",       action="store_true", help="JSON output")
    parsed = parser.parse_args(args)

    results = agent_run(
        parsed.task,
        skip_review=parsed.no_review,
        skip_test=parsed.no_test,
        force_escalate=parsed.escalate,
    )

    if parsed.json:
        print(json.dumps(results, indent=2))
        return

    print("\n" + "─" * 60)
    for key, label in [("programmer", "IMPLEMENTATION"), ("revision", "REVISION"),
                       ("reviewer",   "REVIEW"),         ("tester",   "TEST RESULT")]:
        if key in results and results[key]:
            print(f"\n[{label}]\n")
            print(results[key])

    backend = "Claude (escalated)" if results.get("escalated") else "Qwen3:8b (local)"
    print(f"\n{'─' * 60}\n✓ {backend}\n")


if __name__ == "__main__":
    main()
