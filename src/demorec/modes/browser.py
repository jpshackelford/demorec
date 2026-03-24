"""Browser recording mode using Playwright."""

import asyncio
import json
from pathlib import Path

from ..parser import Command, Segment, parse_time
from . import CommandExecutorMixin, convert_webm_to_mp4


async def _cmd_navigate(page, cmd: Command):
    """Navigate to a URL."""
    if cmd.args:
        await page.goto(cmd.args[0], wait_until="networkidle")


async def _cmd_click(page, cmd: Command):
    """Click an element."""
    if cmd.args:
        await page.click(cmd.args[0])


async def _cmd_type(page, cmd: Command):
    """Type text into an element or keyboard."""
    if len(cmd.args) >= 2:
        await page.type(cmd.args[0], cmd.args[1], delay=50)
    elif len(cmd.args) == 1:
        await page.keyboard.type(cmd.args[0], delay=50)


async def _cmd_fill(page, cmd: Command):
    """Fill an input field."""
    if len(cmd.args) >= 2:
        await page.fill(cmd.args[0], cmd.args[1])


async def _cmd_press(page, cmd: Command):
    """Press a key."""
    if cmd.args:
        await page.keyboard.press(cmd.args[0])


async def _cmd_sleep(page, cmd: Command):
    """Sleep for a duration."""
    if cmd.args:
        await asyncio.sleep(parse_time(cmd.args[0]))


async def _cmd_wait(page, cmd: Command):
    """Wait for a selector."""
    if cmd.args:
        await page.wait_for_selector(cmd.args[0])


async def _cmd_scroll(page, cmd: Command):
    """Scroll the page."""
    direction = cmd.args[0] if cmd.args else "down"
    amount = int(cmd.args[1]) if len(cmd.args) > 1 else 300
    scroll_amount = amount if direction == "down" else -amount
    await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
    await asyncio.sleep(0.3)


async def _cmd_hover(page, cmd: Command):
    """Hover over an element."""
    if cmd.args:
        await page.hover(cmd.args[0])


async def _cmd_highlight(page, cmd: Command):
    """Highlight an element with a red outline."""
    if cmd.args:
        selector = json.dumps(cmd.args[0])
        await page.evaluate(f'document.querySelector({selector}).style.outline = "3px solid red";')


async def _cmd_unhighlight(page, cmd: Command):
    """Remove highlight from an element."""
    if cmd.args:
        selector = json.dumps(cmd.args[0])
        await page.evaluate(f'document.querySelector({selector}).style.outline = "";')


async def _cmd_screenshot(page, cmd: Command):
    """Take a screenshot."""
    filename = cmd.args[0] if cmd.args else "screenshot.png"
    await page.screenshot(path=filename)


# Command dispatch table
BROWSER_COMMANDS = {
    "Navigate": _cmd_navigate,
    "Click": _cmd_click,
    "Type": _cmd_type,
    "Fill": _cmd_fill,
    "Press": _cmd_press,
    "Sleep": _cmd_sleep,
    "Wait": _cmd_wait,
    "Scroll": _cmd_scroll,
    "Hover": _cmd_hover,
    "Highlight": _cmd_highlight,
    "Unhighlight": _cmd_unhighlight,
    "Screenshot": _cmd_screenshot,
}


class BrowserRecorder(CommandExecutorMixin):
    """Records browser sessions using Playwright."""

    def __init__(self, width: int = 1280, height: int = 720, framerate: int = 30):
        self.width = width
        self.height = height
        self.framerate = framerate
        self._timed_narrations = {}

    def record(self, segment: Segment, output: Path, timed_narrations: dict = None):
        """Record a browser segment to video. Returns command timestamps."""
        output = output.absolute()
        self._timed_narrations = timed_narrations or {}
        return asyncio.run(self._record_async(segment, output))

    async def _record_async(self, segment: Segment, output: Path) -> dict[int, tuple[float, float]]:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            context, page = await self._create_browser_context(p, output)
            timestamps = await self._execute_commands(page, segment)
            await context.close()

        self._finalize_video(output)
        return timestamps

    async def _create_browser_context(self, playwright, output: Path):
        """Create browser context with video recording."""
        browser = await playwright.chromium.launch()
        context = await browser.new_context(
            viewport={"width": self.width, "height": self.height},
            record_video_dir=str(output.parent),
            record_video_size={"width": self.width, "height": self.height},
        )
        return context, await context.new_page()

    def _finalize_video(self, output: Path):
        """Find and convert the recorded video."""
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            convert_webm_to_mp4(latest, output)
            latest.unlink()

    async def _execute_command(self, page, cmd: Command):
        """Execute a single browser command."""
        handler = BROWSER_COMMANDS.get(cmd.name)
        if handler:
            await handler(page, cmd)
