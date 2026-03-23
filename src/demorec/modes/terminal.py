"""Terminal recording mode using ttyd + xterm.js for full PTY support.

Uses ttyd to create a real PTY connected to xterm.js in a browser,
enabling full ANSI support, interactive commands, spinners, etc.
"""

import asyncio
import subprocess
import time
from pathlib import Path

from ..parser import Command, Segment
from ..ttyd import check_ttyd, find_free_port, stop_ttyd
from ..xterm import TerminalConfig, fit_to_rows, setup_terminal
from .terminal_commands import TERMINAL_COMMANDS, THEMES
from .vim import VimCommandExpander


class TerminalRecorder:
    """Records terminal sessions using ttyd for full PTY support.

    Uses ttyd to create a real PTY connected to xterm.js in a browser,
    enabling full ANSI support, interactive commands, spinners, colors, etc.
    """

    # Size presets: name -> target rows (for 720p viewport)
    SIZE_PRESETS = {
        "large": 24,  # Classic terminal, easy to read
        "medium": 36,  # Balanced readability and content
        "small": 44,  # Default xterm.js density
        "tiny": 50,  # Maximum content, smaller text
    }

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        framerate: int = 30,
        size: str | None = None,
        rows: int | None = None,
    ):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.theme = "dracula"
        self.font_family = "Monaco, 'Cascadia Code', 'Fira Code', monospace"
        self.line_height = 1.0  # Tight line spacing for consistent row calculation
        self.padding = 20
        self.typing_speed = 0.05  # seconds per character
        self._ttyd_process = None
        self._timed_narrations = {}

        # Convert size preset to target rows, or use explicit row count
        self.size = size
        if rows is not None:
            self.desired_rows = rows
        else:
            self.desired_rows = self.SIZE_PRESETS.get(size) if size else None
        self.font_size = 14  # Default font size, adjusted based on desired rows

        # Vim command expander for high-level primitives
        self._vim_expander = VimCommandExpander(terminal_rows=self.desired_rows or 24)

    def record(
        self, segment: Segment, output: Path, timed_narrations: dict = None
    ) -> dict[int, tuple[float, float]]:
        """Record a terminal segment to video with full PTY support.

        Args:
            segment: The segment to record
            output: Output video file path
            timed_narrations: Dict mapping cmd_index to TimedNarration objects

        Returns:
            Dict mapping command index to (start_time, end_time) in seconds
        """
        output = output.absolute()
        self._timed_narrations = timed_narrations or {}

        if not check_ttyd():
            from ..ttyd import find_ttyd

            find_ttyd()  # Raises with install instructions

        return asyncio.run(self._record_async(segment, output))

    def _apply_theme_from_segment(self, segment: Segment):
        """Apply theme settings from segment commands."""
        for cmd in segment.commands:
            if cmd.name == "SetTheme" and cmd.args:
                theme_name = cmd.args[0].lower().replace(" ", "-")
                if theme_name in THEMES:
                    self.theme = theme_name

    def _start_ttyd(self, port: int):
        """Start ttyd process on the given port."""
        from ..ttyd import start_ttyd

        self._ttyd_process = start_ttyd(port)

    def _cleanup_ttyd(self):
        """Terminate the ttyd process."""
        stop_ttyd(self._ttyd_process)

    async def _run_browser_session(
        self, segment: Segment, output: Path, port: int
    ) -> tuple[dict[int, tuple[float, float]], float]:
        """Run the Playwright browser session to record commands."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            context, page = await self._create_browser_context(p, output)
            video_start_time = time.time()

            await self._wait_for_terminal(page, port)
            term_size = await self._setup_terminal(page)
            self._configure_vim_rows(term_size)
            await self._clear_terminal(page)

            setup_duration = time.time() - video_start_time
            timestamps = await self._execute_commands(page, segment)

            await asyncio.sleep(0.5)
            await context.close()

        return timestamps, setup_duration

    async def _create_browser_context(self, playwright, output: Path):
        """Create browser context with video recording."""
        browser = await playwright.chromium.launch()
        context = await browser.new_context(
            viewport={"width": self.width, "height": self.height},
            device_scale_factor=1,
            record_video_dir=str(output.parent),
            record_video_size={"width": self.width, "height": self.height},
        )
        page = await context.new_page()
        return context, page

    async def _wait_for_terminal(self, page, port: int):
        """Navigate to ttyd and wait for xterm to be ready."""
        await page.goto(f"http://localhost:{port}", wait_until="networkidle")
        await page.wait_for_selector(".xterm-screen", timeout=10000)
        await page.wait_for_function("() => window.term !== undefined", timeout=10000)
        await asyncio.sleep(0.3)

    def _configure_vim_rows(self, term_size: dict | None):
        """Update vim expander with actual terminal rows."""
        if term_size and term_size.get("rows"):
            self._vim_expander.set_terminal_rows(term_size["rows"])

    async def _clear_terminal(self, page):
        """Clear terminal for clean recording start."""
        await page.keyboard.press("Control+l")
        await asyncio.sleep(0.5)

    async def _execute_commands(self, page, segment: Segment) -> dict[int, tuple[float, float]]:
        """Execute commands with timestamp tracking."""
        timestamps: dict[int, tuple[float, float]] = {}
        recording_start = time.time()

        for cmd_idx, cmd in enumerate(segment.commands):
            narration = self._timed_narrations.get(cmd_idx)
            if narration and narration.mode == "before":
                await asyncio.sleep(narration.duration)

            cmd_start = time.time() - recording_start
            await self._execute_command(page, cmd)
            timestamps[cmd_idx] = (cmd_start, time.time() - recording_start)

            if narration and narration.mode == "after":
                await asyncio.sleep(narration.duration)

        return timestamps

    async def _setup_terminal(self, page) -> dict | None:
        """Set up terminal sizing using xterm module."""
        config = TerminalConfig(
            font_size=self.font_size,
            font_family=self.font_family,
            line_height=self.line_height,
            theme=THEMES.get(self.theme),
            desired_rows=self.desired_rows,
        )

        term_size = await setup_terminal(page, config)
        await asyncio.sleep(0.3)

        # Iterative refinement if needed
        if self.desired_rows and term_size and term_size.rows != self.desired_rows:
            term_size = await fit_to_rows(page, self.desired_rows, max_iterations=3)

        if term_size:
            return {"rows": term_size.rows, "cols": term_size.cols, "fontSize": term_size.font_size}
        return None

    def _finalize_video(self, output: Path, trim_start: float = 0):
        """Find and convert the recorded video."""
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            self._convert_to_mp4(latest, output, trim_start=trim_start)
            latest.unlink()

    def _convert_to_mp4(self, webm_path: Path, mp4_path: Path, trim_start: float = 0):
        """Convert webm to mp4 using FFmpeg, optionally trimming the start."""
        cmd = ["ffmpeg", "-y"]
        if trim_start > 0:
            cmd.extend(["-ss", f"{trim_start:.2f}"])
        cmd.extend(
            [
                "-i",
                str(webm_path),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                str(mp4_path),
            ]
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {result.stderr}")

    async def _record_async(self, segment: Segment, output: Path) -> dict[int, tuple[float, float]]:
        """Record terminal session using ttyd and Playwright."""
        self._apply_theme_from_segment(segment)
        port = find_free_port()
        self._start_ttyd(port)
        await asyncio.sleep(0.5)

        try:
            timestamps, setup_duration = await self._run_browser_session(segment, output, port)
        finally:
            self._cleanup_ttyd()

        self._finalize_video(output, trim_start=setup_duration)
        return timestamps

    async def _send_keys(self, page, text: str, delay: float = None):
        """Send keystrokes to the terminal."""
        if delay is None:
            delay = self.typing_speed
        for char in text:
            await page.keyboard.type(char, delay=0)
            if delay > 0:
                await asyncio.sleep(delay)

    async def _execute_command(self, page, cmd: Command):
        """Execute a command in the real PTY."""
        # Check for high-level vim commands first
        if self._vim_expander.is_vim_command(cmd.name):
            expanded = self._vim_expander.expand_command(cmd.name, cmd.args)
            await self._execute_vim_sequence(page, expanded)
            return

        handler = TERMINAL_COMMANDS.get(cmd.name)
        if handler:
            await handler(self, page, cmd)

    async def _execute_vim_sequence(self, page, commands: list[tuple[str, float]]):
        """Execute a sequence of vim keystrokes.

        Args:
            page: Playwright page
            commands: List of (keys, delay_after) tuples
                     Special keys: "ENTER", "ESCAPE", "TAB"
        """
        for keys, delay in commands:
            if keys == "ENTER":
                await page.keyboard.press("Enter")
            elif keys == "ESCAPE":
                await page.keyboard.press("Escape")
            elif keys == "TAB":
                await page.keyboard.press("Tab")
            else:
                await self._send_keys(page, keys, delay=0.02)

            if delay > 0:
                await asyncio.sleep(delay)
