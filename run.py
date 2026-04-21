#!/usr/bin/env python3
"""
Cascade — local-first AI coding agent with Claude escalation.

Usage:
  python3 run.py "write a Python script that monitors disk usage and alerts at 90%"
  python3 run.py "refactor utils.py to use dataclasses" --no-test
  python3 run.py "fix the bug in parser.py" --no-review --no-test
  python3 run.py "build a REST client" --json
"""

import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cascade.agent import run


def main():
    parser = argparse.ArgumentParser(
        description="Cascade — local-first AI coding agent"
    )
    parser.add_argument("task",        help="What to build or fix")
    parser.add_argument("--no-review", action="store_true", help="Skip reviewer role")
    parser.add_argument("--no-test",   action="store_true", help="Skip tester role")
    parser.add_argument("--json",      action="store_true", help="Output results as JSON")
    parser.add_argument("--escalate",  action="store_true", help="Force Claude escalation")
    args = parser.parse_args()

    results = run(
        args.task,
        skip_review=args.no_review,
        skip_test=args.no_test,
        force_escalate=args.escalate,
    )

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print("\n" + "─" * 60)

    for key, label in [("programmer", "IMPLEMENTATION"), ("revision", "REVISION"),
                       ("reviewer", "REVIEW"), ("tester", "TEST RESULT")]:
        if key in results and results[key]:
            print(f"\n[{label}]\n")
            print(results[key])

    backend = "Claude (escalated)" if results.get("escalated") else "Qwen3:8b (local)"
    print(f"\n{'─' * 60}")
    print(f"✓ Completed via {backend}")


if __name__ == "__main__":
    main()
