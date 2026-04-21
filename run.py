#!/usr/bin/env python3
"""
Cascade — local-first AI with Claude escalation.

  cascade               → interactive REPL (like typing 'claude')
  cascade "do a task"   → single task, full agent pipeline
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    if len(sys.argv) == 1:
        # No args — open interactive REPL
        from cascade.repl import run
        run()
    else:
        # Task passed as argument — run agent pipeline
        import argparse, json
        from cascade.agent import run as agent_run

        parser = argparse.ArgumentParser(description="Cascade agent")
        parser.add_argument("task")
        parser.add_argument("--no-review",  action="store_true")
        parser.add_argument("--no-test",    action="store_true")
        parser.add_argument("--escalate",   action="store_true")
        parser.add_argument("--json",       action="store_true")
        args = parser.parse_args()

        results = agent_run(
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
        print(f"\n{'─' * 60}\n✓ {backend}")


if __name__ == "__main__":
    main()
