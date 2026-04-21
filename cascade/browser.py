"""
Browser automation layer — gives Cascade hands to act on the web.
Powered by Playwright (headless Chromium).

Capabilities:
- browse(url) — open a page, return text content
- search(query) — DuckDuckGo search, return top results
- fill_form(url, fields) — fill and submit a form
- screenshot(url) — capture a page screenshot
- run_task(instructions) — Claude-driven multi-step browser task
"""

import asyncio, base64, subprocess, tempfile
from pathlib import Path
from typing import Optional

CLAUDE_BIN = str(Path.home() / ".local" / "bin" / "claude")


async def _browse(url: str, wait: int = 2000) -> tuple[str, str]:
    """Returns (text_content, screenshot_path)."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(wait)

        text = await page.evaluate("""() => {
            const els = document.querySelectorAll('script, style, nav, footer, [aria-hidden]');
            els.forEach(e => e.remove());
            return document.body?.innerText || '';
        }""")

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        await page.screenshot(path=tmp.name, full_page=False)
        await browser.close()
        return text[:8000], tmp.name


async def _fill_form(url: str, fields: dict, submit: bool = True) -> str:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        for selector, value in fields.items():
            try:
                await page.fill(selector, value)
            except Exception as e:
                print(f"  fill error ({selector}): {e}")

        if submit:
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)

        text = await page.evaluate("() => document.body?.innerText || ''")
        await browser.close()
        return text[:4000]


def browse(url: str) -> str:
    text, screenshot = asyncio.run(_browse(url))
    return text


def screenshot(url: str) -> str:
    """Returns path to screenshot file."""
    _, path = asyncio.run(_browse(url))
    return path


def search(query: str) -> str:
    url  = f"https://duckduckgo.com/?q={query.replace(' ', '+')}&ia=web"
    text, _ = asyncio.run(_browse(url))
    return text[:3000]


def fill_form(url: str, fields: dict, submit: bool = True) -> str:
    return asyncio.run(_fill_form(url, fields, submit))


def run_task(instructions: str, start_url: str = "") -> str:
    """
    Claude-driven browser task.
    Claude decides what to navigate to, what to click, what to fill.
    Returns final result.
    """
    prompt = (
        f"You have access to browser tools. Complete this task:\n\n"
        f"{instructions}\n\n"
        + (f"Start at: {start_url}\n\n" if start_url else "")
        + "Use Bash to run Python playwright commands. "
        f"Report what you found or did."
    )
    result = subprocess.run(
        [CLAUDE_BIN, "-p", prompt,
         "--allowedTools", "Bash,Read,Write",
         "--dangerously-skip-permissions"],
        capture_output=True, text=True, timeout=300
    )
    return result.stdout.strip()
