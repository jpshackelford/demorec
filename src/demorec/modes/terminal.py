"""Terminal recording mode using ttyd + xterm.js for full PTY support.

Uses ttyd to create a real PTY connected to xterm.js in a browser,
enabling full ANSI support, interactive commands, spinners, etc.
"""

import asyncio
import os
import socket
import subprocess
import time
from pathlib import Path

from ..parser import Command, Segment, parse_time
from .vim import VimCommandExpander


def _find_free_port() -> int:
    """Find an available port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _check_ttyd() -> bool:
    """Check if ttyd is available."""
    try:
        result = subprocess.run(["ttyd", "--version"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


# Dracula theme
THEMES = {
    "dracula": {
        "background": "#282a36",
        "foreground": "#f8f8f2",
        "cursor": "#f8f8f2",
        "cursorAccent": "#282a36",
        "selectionBackground": "#44475a",
        "black": "#21222c",
        "red": "#ff5555",
        "green": "#50fa7b",
        "yellow": "#f1fa8c",
        "blue": "#bd93f9",
        "magenta": "#ff79c6",
        "cyan": "#8be9fd",
        "white": "#f8f8f2",
        "brightBlack": "#6272a4",
        "brightRed": "#ff6e6e",
        "brightGreen": "#69ff94",
        "brightYellow": "#ffffa5",
        "brightBlue": "#d6acff",
        "brightMagenta": "#ff92df",
        "brightCyan": "#a4ffff",
        "brightWhite": "#ffffff",
    },
    "github-dark": {
        "background": "#0d1117",
        "foreground": "#c9d1d9",
        "cursor": "#c9d1d9",
        "cursorAccent": "#0d1117",
        "selectionBackground": "#3b5070",
        "black": "#484f58",
        "red": "#ff7b72",
        "green": "#3fb950",
        "yellow": "#d29922",
        "blue": "#58a6ff",
        "magenta": "#bc8cff",
        "cyan": "#39c5cf",
        "white": "#b1bac4",
        "brightBlack": "#6e7681",
        "brightRed": "#ffa198",
        "brightGreen": "#56d364",
        "brightYellow": "#e3b341",
        "brightBlue": "#79c0ff",
        "brightMagenta": "#d2a8ff",
        "brightCyan": "#56d4dd",
        "brightWhite": "#f0f6fc",
    },
}


# Terminal command handlers
async def _cmd_set_theme(recorder, page, cmd):
    """SetTheme is processed before recording starts."""
    pass


async def _cmd_type(recorder, page, cmd):
    """Type text into the terminal."""
    if cmd.args:
        await recorder._send_keys(page, cmd.args[0])


async def _cmd_enter(recorder, page, cmd):
    """Press Enter key."""
    await page.keyboard.press("Enter")
    await asyncio.sleep(0.3)


async def _cmd_run(recorder, page, cmd):
    """Type and execute a command."""
    if cmd.args:
        await recorder._send_keys(page, cmd.args[0])
        await page.keyboard.press("Enter")
        wait_time = parse_time(cmd.args[1]) if len(cmd.args) > 1 else 1.0
        await asyncio.sleep(wait_time)


async def _cmd_sleep(recorder, page, cmd):
    """Sleep for a duration."""
    if cmd.args:
        await asyncio.sleep(parse_time(cmd.args[0]))


async def _cmd_ctrl_key(recorder, page, cmd, key: str, delay: float = 0.1):
    """Press a Ctrl+key combination."""
    await page.keyboard.press(f"Control+{key}")
    await asyncio.sleep(delay)


async def _cmd_ctrl_c(recorder, page, cmd):
    await _cmd_ctrl_key(recorder, page, cmd, "c")


async def _cmd_ctrl_d(recorder, page, cmd):
    await _cmd_ctrl_key(recorder, page, cmd, "d")


async def _cmd_ctrl_l(recorder, page, cmd):
    await _cmd_ctrl_key(recorder, page, cmd, "l")


async def _cmd_ctrl_z(recorder, page, cmd):
    await _cmd_ctrl_key(recorder, page, cmd, "z")


async def _cmd_tab(recorder, page, cmd):
    """Press Tab key."""
    await page.keyboard.press("Tab")
    await asyncio.sleep(0.2)


async def _cmd_arrow(recorder, page, cmd, direction: str):
    """Press an arrow key."""
    await page.keyboard.press(f"Arrow{direction}")
    await asyncio.sleep(0.1)


async def _cmd_up(recorder, page, cmd):
    await _cmd_arrow(recorder, page, cmd, "Up")


async def _cmd_down(recorder, page, cmd):
    await _cmd_arrow(recorder, page, cmd, "Down")


async def _cmd_backspace(recorder, page, cmd):
    """Press Backspace key one or more times."""
    count = int(cmd.args[0]) if cmd.args else 1
    for _ in range(count):
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.05)


async def _cmd_escape(recorder, page, cmd):
    """Press Escape key."""
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.1)


async def _cmd_space(recorder, page, cmd):
    """Press Space key."""
    await page.keyboard.press("Space")
    await asyncio.sleep(0.05)


async def _cmd_clear(recorder, page, cmd):
    """Clear the terminal screen."""
    await page.keyboard.press("Control+l")
    await asyncio.sleep(0.1)


# Command dispatch table
TERMINAL_COMMANDS = {
    "SetTheme": _cmd_set_theme,
    "Type": _cmd_type,
    "Enter": _cmd_enter,
    "Run": _cmd_run,
    "Sleep": _cmd_sleep,
    "Ctrl+C": _cmd_ctrl_c,
    "Ctrl+D": _cmd_ctrl_d,
    "Ctrl+L": _cmd_ctrl_l,
    "Ctrl+Z": _cmd_ctrl_z,
    "Tab": _cmd_tab,
    "Up": _cmd_up,
    "Down": _cmd_down,
    "Backspace": _cmd_backspace,
    "Escape": _cmd_escape,
    "Space": _cmd_space,
    "Clear": _cmd_clear,
}


class TerminalRecorder:
    """Records terminal sessions using ttyd for full PTY support.

    Uses ttyd to create a real PTY connected to xterm.js in a browser,
    enabling full ANSI support, interactive commands, spinners, colors, etc.
    """

    # Size presets: name -> target rows (for 720p viewport)
    SIZE_PRESETS = {
        "large": 24,   # Classic terminal, easy to read
        "medium": 36,  # Balanced readability and content
        "small": 44,   # Default xterm.js density
        "tiny": 50,    # Maximum content, smaller text
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

        if not _check_ttyd():
            raise RuntimeError(
                "ttyd not found. Install with:\n"
                "  wget -qO /tmp/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64\n"
                "  chmod +x /tmp/ttyd && sudo mv /tmp/ttyd /usr/local/bin/ttyd"
            )

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
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PS1"] = "$ "
        env["PROMPT_COMMAND"] = ""  # Clear PROMPT_COMMAND that sets PS1JSON

        # Remove any other prompt-related variables that might interfere
        for key in list(env.keys()):
            if "PROMPT" in key and key != "PROMPT_COMMAND":
                del env[key]

        self._ttyd_process = subprocess.Popen(
            [
                "ttyd",
                "--port",
                str(port),
                "--writable",
                "--once",
                "/bin/bash",
                "--norc",
                "--noprofile",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _cleanup_ttyd(self):
        """Terminate the ttyd process."""
        if self._ttyd_process:
            self._ttyd_process.terminate()
            try:
                self._ttyd_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._ttyd_process.kill()

    async def _run_browser_session(
        self, segment: Segment, output: Path, port: int
    ) -> tuple[dict[int, tuple[float, float]], float]:
        """Run the Playwright browser session to record commands.

        Returns:
            Tuple of (timestamps dict, setup_duration in seconds)
        """
        from playwright.async_api import async_playwright

        timestamps: dict[int, tuple[float, float]] = {}
        video_start_time = None
        setup_duration = 0.0

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={"width": self.width, "height": self.height},
                device_scale_factor=1,  # Use 1:1 scale for accurate terminal sizing
                record_video_dir=str(output.parent),
                record_video_size={"width": self.width, "height": self.height},
            )
            page = await context.new_page()

            video_start_time = time.time()
            await page.goto(f"http://localhost:{port}", wait_until="networkidle")
            await page.wait_for_selector(".xterm-screen", timeout=10000)
            await page.wait_for_function("() => window.term !== undefined", timeout=10000)
            await asyncio.sleep(0.3)

            # VHS-style terminal setup with sizing
            term_size = await self._setup_terminal(page)

            # Update vim expander with actual terminal rows
            if term_size and term_size.get("rows"):
                self._vim_expander.set_terminal_rows(term_size["rows"])

            # Clear terminal for clean start
            await page.keyboard.press("Control+l")
            await asyncio.sleep(0.5)

            setup_duration = time.time() - video_start_time
            recording_start = time.time()

            # Execute commands with timestamp tracking
            for cmd_idx, cmd in enumerate(segment.commands):
                narration = self._timed_narrations.get(cmd_idx)

                if narration and narration.mode == "before":
                    await asyncio.sleep(narration.duration)

                cmd_start = time.time() - recording_start
                await self._execute_command(page, cmd)
                cmd_end = time.time() - recording_start
                timestamps[cmd_idx] = (cmd_start, cmd_end)

                if narration and narration.mode == "after":
                    await asyncio.sleep(narration.duration)

            await asyncio.sleep(0.5)
            await context.close()
            await browser.close()

        return timestamps, setup_duration

    async def _setup_terminal(self, page) -> dict | None:
        """Set up terminal sizing using VHS-style approach."""
        term_size = await page.evaluate(
            """(config) => {
            if (!window.term) return null;

            // Make container fill viewport
            const container = document.querySelector('#terminal-container') ||
                              document.querySelector('.xterm');
            if (container) {
                container.style.width = '100vw';
                container.style.height = '100vh';
                container.style.position = 'fixed';
                container.style.top = '0';
                container.style.left = '0';
                container.style.padding = '0';
                container.style.margin = '0';
            }

            const term = window.term;
            term.options.fontFamily = config.fontFamily;
            term.options.lineHeight = config.lineHeight;
            term.options.cursorBlink = false;

            if (config.theme) {
                term.options.theme = config.theme;
            }

            term.fit();
            let baselineRows = term.rows;
            let finalFontSize = config.fontSize;

            if (config.desiredRows && config.desiredRows !== baselineRows) {
                finalFontSize = Math.round(config.fontSize * (baselineRows / config.desiredRows));
                term.options.fontSize = finalFontSize;
                term.fit();
            } else {
                term.options.fontSize = finalFontSize;
                term.fit();
            }

            return {
                rows: term.rows,
                cols: term.cols,
                fontSize: term.options.fontSize,
                baselineRows: baselineRows
            };
        }""",
            {
                "fontSize": self.font_size,
                "fontFamily": self.font_family,
                "lineHeight": self.line_height,
                "theme": THEMES.get(self.theme),
                "desiredRows": self.desired_rows,
            },
        )
        await asyncio.sleep(0.3)

        # Iterative refinement if needed
        if self.desired_rows and term_size and term_size["rows"] != self.desired_rows:
            for _ in range(3):
                term_size = await page.evaluate(
                    """(desiredRows) => {
                    if (!window.term) return null;
                    const term = window.term;
                    const currentRows = term.rows;
                    const currentFontSize = term.options.fontSize || 14;

                    if (currentRows === desiredRows) {
                        return {
                            rows: currentRows, cols: term.cols,
                            fontSize: currentFontSize, done: true
                        };
                    }

                    const newFontSize = Math.round(currentFontSize * (currentRows / desiredRows));
                    term.options.fontSize = newFontSize;
                    term.fit();

                    return {
                        rows: term.rows,
                        cols: term.cols,
                        fontSize: newFontSize,
                        done: term.rows === desiredRows
                    };
                }""",
                    self.desired_rows,
                )
                await asyncio.sleep(0.2)
                if term_size and term_size.get("done"):
                    break

        return term_size

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
        cmd.extend([
            "-i", str(webm_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            str(mp4_path),
        ])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {result.stderr}")

    async def _record_async(self, segment: Segment, output: Path) -> dict[int, tuple[float, float]]:
        """Record terminal session using ttyd and Playwright."""
        self._apply_theme_from_segment(segment)
        port = _find_free_port()
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
