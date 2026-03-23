"""Terminal recording mode using ttyd + xterm.js for full PTY support.

Uses ttyd to create a real PTY connected to xterm.js in a browser,
enabling full ANSI support, interactive commands, spinners, etc.
"""

import asyncio
import os
import socket
import subprocess
from pathlib import Path

from ..parser import Command, Segment, parse_time
from . import convert_webm_to_mp4


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

    def __init__(self, width: int = 1280, height: int = 720, framerate: int = 30):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.theme = "dracula"
        self.font_family = "Monaco, 'Cascadia Code', 'Fira Code', monospace"
        self.font_size = 16
        self.line_height = 1.2
        self.padding = 20
        self.typing_speed = 0.05  # seconds per character
        self._ttyd_process = None

    def record(self, segment: Segment, output: Path):
        """Record a terminal segment to video with full PTY support."""
        output = output.absolute()

        if not _check_ttyd():
            raise RuntimeError(
                "ttyd not found. Install with:\n"
                "  wget -qO /tmp/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64\n"
                "  chmod +x /tmp/ttyd && sudo mv /tmp/ttyd /usr/local/bin/ttyd"
            )

        asyncio.run(self._record_async(segment, output))

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

    async def _run_browser_session(self, segment: Segment, output: Path, port: int):
        """Run the Playwright browser session to record commands."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={"width": self.width, "height": self.height},
                device_scale_factor=2,
                record_video_dir=str(output.parent),
                record_video_size={"width": self.width, "height": self.height},
            )
            page = await context.new_page()
            await page.goto(f"http://localhost:{port}", wait_until="networkidle")
            await page.wait_for_selector(".xterm-screen", timeout=10000)
            await asyncio.sleep(1.0)

            for cmd in segment.commands:
                await self._execute_command(page, cmd)

            await asyncio.sleep(0.5)
            await context.close()
            await browser.close()

    def _finalize_video(self, output: Path):
        """Find and convert the recorded video."""
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            convert_webm_to_mp4(latest, output)
            latest.unlink()

    async def _record_async(self, segment: Segment, output: Path):
        """Record terminal session using ttyd and Playwright."""
        self._apply_theme_from_segment(segment)
        port = _find_free_port()
        self._start_ttyd(port)
        await asyncio.sleep(0.5)

        try:
            await self._run_browser_session(segment, output, port)
        finally:
            self._cleanup_ttyd()

        self._finalize_video(output)

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
        handler = TERMINAL_COMMANDS.get(cmd.name)
        if handler:
            await handler(self, page, cmd)
