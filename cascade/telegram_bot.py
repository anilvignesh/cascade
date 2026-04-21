"""
Cascade Telegram bot.
Send queries from your phone → Qwen3 or Claude responds → reply lands in Telegram.
All exchanges saved to MemPalace.

Setup:
  1. Message @BotFather on Telegram → /newbot → copy the token
  2. Get your chat ID: message @userinfobot
  3. Set env vars or edit TELEGRAM_TOKEN / ALLOWED_CHAT_ID below
  4. Run: cascade bot
"""

import os, asyncio, textwrap
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from telegram.constants import ParseMode

from .repl import ask, mem_save, route

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
ALLOWED_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))

MAX_MSG = 4000  # Telegram message length limit


def _split(text: str) -> list[str]:
    """Split long responses into chunks Telegram can handle."""
    return textwrap.wrap(text, MAX_MSG, break_long_words=False, replace_whitespace=False) or [text]


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "◆ Cascade online.\n"
        "Send any message — Qwen3 handles it locally, Claude steps in when needed.\n"
        "Prefix with !! to force Claude.\n\n"
        "/status — agent status\n/history — recent queries"
    )


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import json
    from pathlib import Path
    state_file = Path.home() / "cascade" / ".agent" / "worker-state.json"
    if state_file.exists():
        try:
            d = json.loads(state_file.read_text())
            msg = (
                f"*Cascade Status*\n"
                f"Status: `{d.get('status','?')}`\n"
                f"Backend: `{d.get('backend','?')}`\n"
                f"Last task: `{d.get('task','?')[:60]}`\n"
                f"Updated: `{d.get('updated_at','?')}`"
            )
        except Exception as e:
            msg = f"State file unreadable: {e}"
    else:
        msg = "No active agent state."

    # Check Ollama
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        msg += "\nOllama: ✓ running"
    except Exception:
        msg += "\nOllama: ✗ offline"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def history_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from .repl import mem_search
    mem = mem_search("cascade recent")
    if mem:
        await update.message.reply_text(f"*Recent memory:*\n{mem[:1500]}", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("No memory found yet.")


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Auth check
    if ALLOWED_CHAT_ID and update.effective_chat.id != ALLOWED_CHAT_ID:
        await update.message.reply_text("Unauthorised.")
        return

    query = update.message.text.strip()
    if not query:
        return

    force_claude = query.startswith("!!")
    if force_claude:
        query = query[2:].strip()

    # Show typing indicator
    await ctx.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Route indicator
    mode = "claude" if force_claude else route(query)
    backend_label = "Claude" if mode == "claude" else "Qwen3"
    await update.message.reply_text(
        f"_{backend_label} thinking…_", parse_mode=ParseMode.MARKDOWN
    )

    try:
        if force_claude:
            from .llm import call_claude
            response = call_claude(query)
            backend  = "claude"
        else:
            response, backend = ask(query)

        mem_save(query, response, backend)

        label = "Claude ↑" if backend == "claude" else "Qwen3 local"
        for chunk in _split(response):
            await update.message.reply_text(
                f"{chunk}\n\n_{label}_", parse_mode=ParseMode.MARKDOWN
            )

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


def run():
    if not TELEGRAM_TOKEN:
        print(
            "\nTELEGRAM_TOKEN not set.\n"
            "1. Message @BotFather → /newbot → copy token\n"
            "2. Message @userinfobot → copy your chat ID\n"
            "3. Run:\n"
            "   export TELEGRAM_TOKEN=your_token\n"
            "   export TELEGRAM_CHAT_ID=your_chat_id\n"
            "   cascade bot\n"
        )
        return

    print(f"◆ Cascade Telegram bot starting…")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("status",  status_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"  Bot running. Send a message on Telegram to start.")
    app.run_polling(drop_pending_updates=True)
