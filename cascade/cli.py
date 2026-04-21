#!/usr/bin/env python3
"""
Cascade — local-first AI with Claude escalation + MemPalace memory.

  cascade               → interactive REPL
  cascade "do a task"   → single task, full agent pipeline
  cascade status        → agent + system dashboard
  cascade bot           → start Telegram bot
  cascade watch         → run job + news watcher once
  cascade brief         → send morning brief to Telegram
  cascade reminders     → check due reminders + send alerts
  cascade remind <text> → add a new reminder (natural language date)
  cascade skills        → list available skills
  cascade learn         → analyse memory, update context.md with learned patterns
  cascade agent <name> "task" → run a named agent directly
  cascade agents        → list available agents
  cascade init          → auto-detect CLIs, write config.yml
"""

import sys


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

    if args[0] == "watch":
        from cascade.watcher import run
        run()
        return

    if args[0] == "brief":
        from cascade.brief import run
        run()
        return

    if args[0] == "reminders":
        from cascade.reminders import check_due
        check_due()
        return

    if args[0] == "remind":
        from cascade.reminders import add
        text = " ".join(args[1:])
        if not text:
            print("Usage: cascade remind <text> (include date like 'Friday' or 'tomorrow')")
        else:
            print(add(text))
        return

    if args[0] == "init":
        from cascade.init_cmd import run as init_run
        init_run()
        return

    if args[0] == "agents":
        from cascade.agents import list_agents
        agents = list_agents()
        if agents:
            print("\nAvailable agents:")
            for name, desc in agents.items():
                print(f"  {name:<16} {desc}")
        print()
        return

    if args[0] == "agent":
        if len(args) < 3:
            print("Usage: cascade agent <name> \"task\"")
            return
        from cascade.agents import get_agent
        name, task = args[1], " ".join(args[2:])
        agent = get_agent(name)
        print(f"\n◆ AGENT [{name}] — {task[:60]}\n")
        response, escalated = agent.run(task)
        print(response)
        if escalated:
            print("\n  [escalated to coder]")
        return

    if args[0] == "learn":
        from cascade.learn import run as learn_run
        learn_run()
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

    # ── Orchestrator (task as argument) ──
    from cascade.agents import Orchestrator
    task = " ".join(args)
    result = Orchestrator().run(task)
    print("\n" + result)


if __name__ == "__main__":
    main()
