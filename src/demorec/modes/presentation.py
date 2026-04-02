"""Presentation recording mode using Marp + Playwright."""

import asyncio
import logging
import time
from pathlib import Path
from urllib.parse import quote

from ..marp import render_to_html
from ..parser import Command, Segment, parse_time
from . import CommandExecutorMixin, convert_webm_to_mp4

logger = logging.getLogger(__name__)

# Timing constants
SLIDE_TRANSITION_DELAY = 0.3  # Allow Marp CSS transitions to complete after navigation
NARRATION_PADDING = 0.5  # Extra buffer time after narration completes


async def _cmd_slide(page, cmd: Command, recorder: "PresentationRecorder"):
    """Navigate to a specific slide."""
    slide_num = int(cmd.args[0])
    await recorder._goto_slide(page, slide_num)


async def _cmd_sleep(page, cmd: Command, recorder: "PresentationRecorder"):
    """Sleep for a duration."""
    if cmd.args:
        await asyncio.sleep(parse_time(cmd.args[0]))


PRESENTATION_COMMANDS = {
    "Slide": _cmd_slide,
    "Sleep": _cmd_sleep,
}


class PresentationRecorder(CommandExecutorMixin):
    """Records Marp presentations using Playwright."""

    def __init__(self, width: int = 1920, height: int = 1080, framerate: int = 30):
        self.width = width
        self.height = height
        self.framerate = framerate
        self._timed_narrations = {}
        self._current_slide = 0
        self._html_path: Path | None = None

    def record(self, segment: Segment, output: Path, timed_narrations: dict = None):
        """Record a presentation segment to video."""
        output = output.absolute()
        self._timed_narrations = timed_narrations or {}
        return asyncio.run(self._record_async(segment, output))

    async def _record_async(self, segment: Segment, output: Path) -> dict:
        self._html_path = render_to_html(
            segment.presentation_file, output.parent, theme=segment.presentation_theme
        )
        timestamps = await self._record_with_playwright(segment, output)
        self._finalize_video(output)
        return timestamps

    async def _record_with_playwright(self, segment: Segment, output: Path) -> dict:
        """Run Playwright recording session."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            context, page = await self._create_browser_context(p, output)
            await page.goto(self._file_url(), wait_until="load")
            await asyncio.sleep(0.5)
            timestamps = await self._execute_commands_with_timing(page, segment)
            await context.close()
        return timestamps

    def _file_url(self, fragment: str | None = None) -> str:
        """Build properly encoded file:// URL for the HTML path."""
        encoded = quote(str(self._html_path), safe="/:")
        return f"file://{encoded}#{fragment}" if fragment else f"file://{encoded}"

    async def _create_browser_context(self, playwright, output: Path):
        """Create browser context with video recording."""
        browser = await playwright.chromium.launch()
        context = await browser.new_context(
            viewport={"width": self.width, "height": self.height},
            record_video_dir=str(output.parent),
            record_video_size={"width": self.width, "height": self.height},
        )
        return context, await context.new_page()

    async def _goto_slide(self, page, target: int):
        """Navigate to a specific slide number."""
        if target == self._current_slide:
            return
        await page.goto(self._file_url(str(target)))
        await asyncio.sleep(SLIDE_TRANSITION_DELAY)
        self._current_slide = target

    async def _execute_commands_with_timing(self, page, segment: Segment) -> dict:
        """Execute commands with smart timing for narration."""
        timestamps = {}
        start = time.time()

        for idx, cmd in enumerate(segment.commands):
            await self._handle_narration_before(idx)
            cmd_start = time.time() - start

            await self._execute_command(page, cmd)

            if cmd.name == "Slide":
                await self._smart_wait(cmd, idx)

            timestamps[idx] = (cmd_start, time.time() - start)
            await self._handle_narration_after(idx)

        return timestamps

    async def _smart_wait(self, cmd: Command, cmd_idx: int):
        """Wait the longer of min_time or narration duration + padding."""
        min_time = parse_time(cmd.args[1]) if len(cmd.args) > 1 else 0
        narration = self._timed_narrations.get(cmd_idx)

        if narration and narration.mode == "during":
            actual_wait = max(min_time, narration.duration + NARRATION_PADDING)
        else:
            actual_wait = min_time

        if actual_wait > 0:
            await asyncio.sleep(actual_wait)

    async def _execute_command(self, page, cmd: Command):
        """Execute a single presentation command."""
        handler = PRESENTATION_COMMANDS.get(cmd.name)
        if handler:
            await handler(page, cmd, self)

    def _finalize_video(self, output: Path):
        """Find and convert the recorded video."""
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            try:
                convert_webm_to_mp4(latest, output)
                latest.unlink()
            except Exception:
                logger.error("Conversion failed, webm preserved at %s", latest)
                raise
