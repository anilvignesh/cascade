#!/usr/bin/env python3
"""
Cascade — local-first AI coding agent with Claude escalation.

Usage:
  python run.py "write a Python script that monitors disk usage and alerts at 90%"
  python run.py "refactor utils.py to use dataclasses" --no-test
  python run.py "fix the bug in parser.py" --no-review --no-test
"""

import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cascade.agent import run


def main():
    parser = argparse.ArgumentParser(
        description="Cascade — local-first AI coding agent"
    )
    parser.add_argument("task", help="What to build or fix")
    parser.add_argument("--no-review", action="store_true", help="Skip review role")
    parser.add_argument("--no-test",   action="store_true", help="Skip tester role")
    parser.add_argument("--json",      action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    results = run(
        args.task,
        skip_review=args.no_review,
        skip_test=args.no_test,
    )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("\n" + "─" * 60)
        if "programmer" in results:
            print("\n[IMPLEMENTATION]\n")
            print(results["programmer"])
        if "reviewer" in results:
            print("\n[REVIEW]\n")
            print(results["reviewer"])
        if "tester" in results:
            print("\n[TEST RESULT]\n")
            print(results["tester"])
        backend = "Claude (escalated)" if results.get("escalated") else "Qwen3 (local)"
        print(f"\n✓ Completed via {backend}")


if __name__ == "__main__":
    main()
