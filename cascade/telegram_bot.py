"""
Cascade Telegram bot — handles text, documents, voice, and images.
Powered by Qwen3 locally, escalates to Claude when needed.
All exchanges saved to MemPalace.

Setup:
  export TELEGRAM_TOKEN=...
  export TELEGRAM_CHAT_ID=...
  cascade bot
"""

import os, asyncio, textwrap, logging, tempfile
from datetime import datetime
from pathlib import Path

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

# Load ~/.cascade.env
_env_file = Path.home() / ".cascade.env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from telegram.constants import ParseMode

from .repl    import ask_local, ask_claude, mem_save, route
from .profile import load as load_profile
from .llm     import call_claude
from .parsers import extract

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
ALLOWED_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
MAX_MSG         = 4000


def _chunks(text: str) -> list[str]:
    if len(text) <= MAX_MSG:
        return [text]
    return [text[i:i+MAX_MSG] for i in range(0, len(text), MAX_MSG)]


def _auth(update: Update) -> bool:
    if not ALLOWED_CHAT_ID:
        return True
    return update.effective_chat.id == ALLOWED_CHAT_ID


async def _typing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )


async def _reply(update: Update, text: str, backend: str = ""):
    label = {"claude": "_via Claude_", "local": "_via Qwen3_"}.get(backend, "")
    for i, chunk in enumerate(_chunks(text)):
        suffix = f"\n\n{label}" if label and i == len(_chunks(text)) - 1 else ""
        try:
            await update.message.reply_text(
                chunk + suffix, parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            await update.message.reply_text(chunk + suffix)


async def _respond(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                   query: str, force_claude: bool = False, file_context: str = ""):
    session = ctx.chat_data.get("session", [])
    full_query = f"{file_context}\n\n{query}".strip() if file_context else query

    mode = "claude" if force_claude else route(full_query)

    await _typing(update, ctx)
    try:
        if mode == "claude":
            response = ask_claude(full_query, session)
            backend  = "claude"
        else:
            response = ask_local(full_query, session)
            backend  = "local"

        session.extend([
            {"role": "user",      "content": full_query[:500]},
            {"role": "assistant", "content": response[:500]},
        ])
        ctx.chat_data["session"] = session[-12:]

        mem_save(query, response, backend)
        await _reply(update, response, backend)

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# ── Commands ──────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    await update.message.reply_text(
        "◆ *Cascade* — local-first AI\n\n"
        "Send me anything:\n"
        "• A question or task\n"
        "• A document (PDF, DOCX) — I'll read it\n"
        "• A voice message — I'll transcribe and answer\n"
        "• A resume + 'find matching jobs'\n\n"
        "Prefix with `!!` to force Claude for hard tasks.\n\n"
        "/status · /history · /clear · /skills",
        parse_mode=ParseMode.MARKDOWN
    )


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    import json, urllib.request
    lines = ["*Cascade Status*\n"]
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        lines.append("Ollama: ✓ running")
    except Exception:
        lines.append("Ollama: ✗ offline")

    state_file = Path.home() / "cascade" / ".agent" / "worker-state.json"
    if state_file.exists():
        try:
            d = json.loads(state_file.read_text())
            lines.append(f"Agent: `{d.get('status','?')}` [{d.get('backend','?')}]")
            lines.append(f"Last: `{d.get('task','?')[:50]}`")
        except Exception:
            pass

    session = ctx.chat_data.get("session", [])
    lines.append(f"Session turns: {len(session) // 2}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def history_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    from .repl import mem_search
    mem = mem_search("cascade recent")
    await update.message.reply_text(
        f"*Recent memory:*\n{mem[:1500]}" if mem else "No memory yet.",
        parse_mode=ParseMode.MARKDOWN
    )


async def clear_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    ctx.chat_data["session"] = []
    await update.message.reply_text("Session cleared.")


async def skills_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    from .skills import list_skills
    skills = list_skills()
    lines  = ["*Available skills:*\n"]
    for name, desc in skills.items():
        lines.append(f"`/{name}` — {desc}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


CONFIRM_PHRASE = "jarvis do it"

SYSTEM_KEYWORDS = [
    "install ", "uninstall ", "upgrade ", "update ", "apt ", "pip install",
    "ollama pull", "ollama rm", "sudo ", "reboot", "shutdown", "restart ",
    "rm -", "delete ", "kill ", "pkill", "systemctl"
]

def _is_system_task(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in SYSTEM_KEYWORDS)


async def _plan_system_task(query: str) -> str:
    """Ask Claude to determine the exact command to run."""
    from .llm import call_claude
    response = call_claude(
        f"The user wants to: {query}\n\n"
        f"Respond with ONLY the exact bash command to run. "
        f"Nothing else — no explanation, no markdown, just the command."
    )
    return response.strip().strip("`").strip()


async def _execute_command(command: str) -> str:
    import subprocess
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=120
        )
        out = (result.stdout + result.stderr).strip()
        return out[:3000] if out else "Done (no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 120s"
    except Exception as e:
        return f"Execution error: {e}"


# ── Message handlers ──────────────────────────────────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        if not ALLOWED_CHAT_ID:
            cid = update.effective_chat.id
            logging.info(f"First message from {cid}")
            await update.message.reply_text(
                f"✓ Connected! Your chat ID: `{cid}`\n"
                f"Set `TELEGRAM_CHAT_ID={cid}` in `~/.cascade.env` and restart.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("Unauthorised.")
        return

    query = update.message.text.strip()
    if not query:
        return

    # ── Confirmation for pending system command ──
    pending = ctx.chat_data.get("pending_command")
    if pending:
        if query.lower() == CONFIRM_PHRASE:
            ctx.chat_data.pop("pending_command", None)
            await _typing(update, ctx)
            await update.message.reply_text(f"_Running…_\n`{pending}`", parse_mode=ParseMode.MARKDOWN)
            output = await _execute_command(pending)
            await _reply(update, f"```\n{output}\n```")
            mem_save(f"system: {pending}", output, "bash")
        else:
            ctx.chat_data.pop("pending_command", None)
            await update.message.reply_text("_Cancelled._", parse_mode=ParseMode.MARKDOWN)
        return

    # ── Skill invocation ──
    from .skills import detect_skill, run_skill
    skill_name = detect_skill(query)
    if skill_name:
        skill_query = " ".join(query.split()[1:])
        await _typing(update, ctx)
        response = run_skill(skill_name, skill_query)
        await _reply(update, response)
        return

    # ── System task detection ──
    force_claude = query.startswith("!!")
    clean_query  = query[2:].strip() if force_claude else query

    if _is_system_task(clean_query):
        await _typing(update, ctx)
        command = await _plan_system_task(clean_query)
        ctx.chat_data["pending_command"] = command
        await update.message.reply_text(
            f"This will run on your laptop:\n`{command}`\n\nReply *{CONFIRM_PHRASE}* to confirm, or anything else to cancel.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await _respond(update, ctx, clean_query, force_claude=force_claude)


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return

    doc      = update.message.document
    caption  = (update.message.caption or "").strip()
    mime     = doc.mime_type or ""

    await _typing(update, ctx)
    await update.message.reply_text(f"_Reading {doc.file_name}…_", parse_mode=ParseMode.MARKDOWN)

    try:
        tg_file = await ctx.bot.get_file(doc.file_id)
        suffix  = Path(doc.file_name).suffix if doc.file_name else ".bin"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            await tg_file.download_to_drive(tmp.name)
            content = extract(tmp.name, mime)
            Path(tmp.name).unlink(missing_ok=True)

        if not content or "error" in content.lower()[:20]:
            await update.message.reply_text(f"Couldn't read file: {content}")
            return

        # Build query: caption or smart default based on file type
        if caption:
            query = caption
        elif "resume" in doc.file_name.lower() or "cv" in doc.file_name.lower():
            query = "This is my resume. Find matching jobs from the current job listings and rank them by fit. Explain why each is a good match."
        else:
            query = f"I've uploaded a file called '{doc.file_name}'. Summarise the key points and tell me what's most important."

        file_context = f"[File: {doc.file_name}]\n{content[:4000]}"
        await _respond(update, ctx, query, force_claude=True, file_context=file_context)

    except Exception as e:
        await update.message.reply_text(f"File handling error: {e}")


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return

    await _typing(update, ctx)
    await update.message.reply_text("_Transcribing…_", parse_mode=ParseMode.MARKDOWN)

    try:
        voice   = update.message.voice
        tg_file = await ctx.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await tg_file.download_to_drive(tmp.name)
            transcript = extract(tmp.name, "audio")
            Path(tmp.name).unlink(missing_ok=True)

        if not transcript or "error" in transcript.lower()[:20]:
            await update.message.reply_text(f"Transcription failed: {transcript}")
            return

        await update.message.reply_text(f"_You said: {transcript}_", parse_mode=ParseMode.MARKDOWN)
        await _respond(update, ctx, transcript)

    except Exception as e:
        await update.message.reply_text(f"Voice handling error: {e}")


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return

    caption = (update.message.caption or "What is in this image?").strip()
    await _typing(update, ctx)

    try:
        photo   = update.message.photo[-1]  # highest resolution
        tg_file = await ctx.bot.get_file(photo.file_id)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await tg_file.download_to_drive(tmp.name)
            img_path = tmp.name

        # Claude can handle images via file path prompt
        response = call_claude(
            f"The user sent an image with caption: '{caption}'. "
            f"Image saved at: {img_path}. "
            f"Read the image and respond to the caption."
        )
        Path(img_path).unlink(missing_ok=True)
        await _reply(update, response, "claude")

    except Exception as e:
        await update.message.reply_text(f"Image handling error: {e}")


# ── Runner ────────────────────────────────────────────────────────────────────

def run():
    if not TELEGRAM_TOKEN:
        print(
            "\nTELEGRAM_TOKEN not set.\n"
            "1. Message @BotFather → /newbot → copy token\n"
            "2. Set in ~/.cascade.env:\n"
            "   TELEGRAM_TOKEN=your_token\n"
            "   TELEGRAM_CHAT_ID=your_chat_id\n"
            "3. Run: cascade bot\n"
        )
        return

    print("◆ Cascade Telegram bot starting…")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("status",  status_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("clear",   clear_cmd))
    app.add_handler(CommandHandler("skills",  skills_cmd))

    app.add_handler(MessageHandler(filters.TEXT    & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL,               handle_document))
    app.add_handler(MessageHandler(filters.VOICE,                      handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO,                      handle_photo))

    print("  Bot running. Handles text, documents, voice, and images.")
    app.run_polling(drop_pending_updates=True)
