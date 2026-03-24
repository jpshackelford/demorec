"""Terminal recording mode using ttyd + xterm.js for full PTY support.

Uses ttyd to create a real PTY connected to xterm.js in a browser,
enabling full ANSI support, interactive commands, spinners, etc.

Supports persistent sessions across mode switches and multiple named sessions.
"""

import asyncio
import subprocess
import time
from pathlib import Path

from ..parser import Command, Segment
from ..ttyd import check_ttyd, find_free_port, start_ttyd, stop_ttyd
from ..xterm import TerminalConfig, fit_to_rows, setup_terminal
from . import CommandExecutorMixin
from .terminal_commands import TERMINAL_COMMANDS, THEMES
from .vim import VimCommandExpander


class TerminalSession:
    """Manages a single persistent terminal session via ttyd.

    The session persists across multiple recording segments, preserving
    working directory, environment variables, and terminal history.
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self.port = find_free_port()
        self._process: subprocess.Popen | None = None
        self._started = False

    def start(self) -> None:
        """Start the ttyd process for this session."""
        if self._started:
            return
        if not check_ttyd():
            from ..ttyd import find_ttyd
            find_ttyd()  # Raises with install instructions
        self._process = start_ttyd(self.port)
        self._started = True

    def stop(self) -> None:
        """Stop the ttyd process."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._started = False

    def is_running(self) -> bool:
        """Check if the ttyd process is still running."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def __repr__(self) -> str:
        status = "running" if self.is_running() else "stopped"
        return f"TerminalSession(name={self.name!r}, port={self.port}, {status})"


class TerminalSessionManager:
    """Manages multiple named terminal sessions.

    Sessions persist for the lifetime of the manager, allowing terminal
    state to be preserved across mode switches (terminal -> browser -> terminal).

    Example:
        manager = TerminalSessionManager()
        server = manager.get_or_create("server")  # Creates new session
        client = manager.get_or_create("client")  # Creates another session
        server2 = manager.get_or_create("server") # Returns existing session
        manager.cleanup()  # Stops all sessions
    """

    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}

    def get_or_create(self, name: str = "default") -> TerminalSession:
        """Get an existing session or create a new one.

        Args:
            name: Session name (e.g., "default", "server", "client")

        Returns:
            The terminal session, started and ready to use.
        """
        if name not in self._sessions:
            session = TerminalSession(name)
            session.start()
            self._sessions[name] = session

        session = self._sessions[name]

        # Restart if session died
        if not session.is_running():
            session.start()

        return session

    def cleanup(self) -> None:
        """Stop all terminal sessions."""
        for session in self._sessions.values():
            session.stop()
        self._sessions.clear()

    def __len__(self) -> int:
        return len(self._sessions)

    def __repr__(self) -> str:
        return f"TerminalSessionManager({list(self._sessions.keys())})"


class TerminalRecorder(CommandExecutorMixin):
    """Records terminal sessions using ttyd for full PTY support.

    Uses ttyd to create a real PTY connected to xterm.js in a browser,
    enabling full ANSI support, interactive commands, spinners, colors, etc.

    Supports persistent sessions via TerminalSessionManager, preserving
    terminal state across mode switches.
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
        session_manager: TerminalSessionManager | None = None,
        session_name: str = "default",
    ):
        self._init_dimensions(width, height, framerate)
        self._init_theme_settings()
        self._init_row_settings(size, rows)
        self._vim_expander = VimCommandExpander(terminal_rows=self.desired_rows or 24)
        self.session_manager = session_manager
        self.session_name = session_name

    def _init_dimensions(self, width: int, height: int, framerate: int):
        """Initialize dimension settings."""
        self.width, self.height, self.framerate = width, height, framerate

    def _init_theme_settings(self):
        """Initialize theme and font settings."""
        self.theme = "dracula"
        self.font_family = "Monaco, 'Cascadia Code', 'Fira Code', monospace"
        self.line_height, self.padding, self.typing_speed = 1.0, 20, 0.05
        self._ttyd_process, self._timed_narrations = None, {}

    def _init_row_settings(self, size: str | None, rows: int | None):
        """Initialize row and font size settings."""
        self.size = size
        self.desired_rows = rows if rows else (self.SIZE_PRESETS.get(size) if size else None)
        self.font_size = 14

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
            setup_dur, timestamps = await self._record_with_timing(page, port, segment)
            await asyncio.sleep(0.5)
            await context.close()
        return timestamps, setup_dur

    async def _record_with_timing(self, page, port: int, segment: Segment):
        """Record session and return setup duration and timestamps."""
        video_start = time.time()
        await self._wait_for_terminal(page, port)
        term_size = await self._setup_terminal(page)
        self._configure_vim_rows(term_size)
        await self._clear_terminal(page)
        setup_dur = time.time() - video_start
        return setup_dur, await self._execute_commands(page, segment)

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

    async def _setup_terminal(self, page) -> dict | None:
        """Set up terminal sizing using xterm module."""
        config = self._build_terminal_config()
        term_size = await setup_terminal(page, config)
        await asyncio.sleep(0.3)
        term_size = await self._refine_rows(page, term_size)
        return self._term_size_to_dict(term_size) if term_size else None

    def _build_terminal_config(self) -> TerminalConfig:
        """Build terminal configuration."""
        return TerminalConfig(
            font_size=self.font_size,
            font_family=self.font_family,
            line_height=self.line_height,
            theme=THEMES.get(self.theme),
            desired_rows=self.desired_rows,
        )

    async def _refine_rows(self, page, term_size):
        """Iteratively refine terminal rows if needed."""
        if self.desired_rows and term_size and term_size.rows != self.desired_rows:
            return await fit_to_rows(page, self.desired_rows, max_iterations=3)
        return term_size

    def _term_size_to_dict(self, term_size) -> dict:
        """Convert TerminalSize to dictionary."""
        return {"rows": term_size.rows, "cols": term_size.cols, "fontSize": term_size.font_size}

    def _finalize_video(self, output: Path, trim_start: float = 0):
        """Find and convert the recorded video."""
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            self._convert_to_mp4(latest, output, trim_start=trim_start)
            latest.unlink()

    def _convert_to_mp4(self, webm_path: Path, mp4_path: Path, trim_start: float = 0):
        """Convert webm to mp4 using FFmpeg, optionally trimming the start."""
        cmd = self._build_convert_cmd(webm_path, mp4_path, trim_start)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {result.stderr}")

    def _build_convert_cmd(  # length-ok
        self, webm_path: Path, mp4_path: Path, trim_start: float
    ) -> list:
        """Build FFmpeg conversion command."""
        trim_args = ["-ss", f"{trim_start:.2f}"] if trim_start > 0 else []
        return [
            "ffmpeg",
            "-y",
            *trim_args,
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

    async def _record_async(self, segment: Segment, output: Path) -> dict[int, tuple[float, float]]:
        """Record terminal session using ttyd and Playwright.

        If session_manager is provided, uses persistent sessions that preserve
        terminal state across mode switches. Otherwise, creates a one-shot session.
        """
        self._apply_theme_from_segment(segment)

        # Use persistent session if manager provided, otherwise create one-shot session
        if self.session_manager:
            session = self.session_manager.get_or_create(self.session_name)
            port = session.port
            await asyncio.sleep(0.3)  # Give session time if just started
            owns_session = False
        else:
            port = find_free_port()
            self._start_ttyd(port)
            await asyncio.sleep(0.5)
            owns_session = True

        try:
            timestamps, setup_duration = await self._run_browser_session(segment, output, port)
        finally:
            # Only cleanup if we created the session (not using session_manager)
            if owns_session:
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
        """Execute a sequence of vim keystrokes with optional delays."""
        special_keys = {"ENTER": "Enter", "ESCAPE": "Escape", "TAB": "Tab"}
        for keys, delay in commands:
            if keys in special_keys:
                await page.keyboard.press(special_keys[keys])
            else:
                await self._send_keys(page, keys, delay=0.02)
            if delay > 0:
                await asyncio.sleep(delay)
