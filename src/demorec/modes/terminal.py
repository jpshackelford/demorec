"""Terminal recording mode using ttyd + xterm.js for full PTY support.

Uses ttyd to create a real PTY connected to xterm.js in a browser,
enabling full ANSI support, interactive commands, spinners, etc.
"""

import asyncio
import subprocess
import tempfile
import signal
import socket
import time
import os
from pathlib import Path

from ..parser import Segment, Command, parse_time
from ..js import TERMINAL_RESIZE_JS
from .vim import VimCommandExpander
from .recording import execute_with_narration_timing


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
    
    def __init__(self, width: int = 1280, height: int = 720, framerate: int = 30, 
                 size: str | None = None, rows: int | None = None):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.theme = "dracula"
        self.font_family = "Monaco, 'Cascadia Code', 'Fira Code', monospace"
        self.line_height = 1.0  # Tight line spacing for consistent row calculation
        self.padding = 20
        self.typing_speed = 0.05  # seconds per character
        self._ttyd_process = None
        
        # Convert size preset to target rows, or use explicit row count
        self.size = size
        # Explicit rows override size preset
        if rows is not None:
            self.desired_rows = rows
        else:
            self.desired_rows = self.SIZE_PRESETS.get(size) if size else None
        self.font_size = 14  # Default font size, will be adjusted based on desired rows
        
        # Vim command expander for high-level primitives
        self._vim_expander = VimCommandExpander(
            terminal_rows=self.desired_rows or 24
        )
    
    def record(self, segment: Segment, output: Path, timed_narrations: dict = None) -> dict[int, tuple[float, float]]:
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
    
    def _create_ttyd_env(self) -> dict:
        """Create clean environment for ttyd subprocess.
        
        Uses explicit whitelist to avoid PS1JSON and other prompt artifacts.
        """
        # Start with minimal required environment
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "TERM": "xterm-256color",
            "PS1": "$ ",
            "PROMPT_COMMAND": "",
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        }
        # Add SHELL if present
        if "SHELL" in os.environ:
            env["SHELL"] = os.environ["SHELL"]
        return env
    
    def _start_ttyd(self, port: int, env: dict) -> subprocess.Popen:
        """Start ttyd subprocess on the given port."""
        ttyd_cmd = [
            "ttyd",
            "--port", str(port),
            "--writable",
            "--once",
            "/bin/bash", "--norc", "--noprofile"
        ]
        return subprocess.Popen(
            ttyd_cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    
    async def _initialize_terminal(self, page) -> dict | None:
        """Initialize terminal with theme, fonts, and desired row count.
        
        Args:
            page: Playwright page object connected to ttyd
            
        Returns:
            Terminal size dict with rows, cols, fontSize, or None on failure
        """
        # Load terminal resize functions from external JS
        await page.evaluate(TERMINAL_RESIZE_JS)
        
        # Initialize terminal with VHS-style setup
        term_size = await page.evaluate(
            "config => initializeTerminal(config)",
            {
                "fontSize": self.font_size,
                "fontFamily": self.font_family,
                "lineHeight": self.line_height,
                "theme": THEMES.get(self.theme),
                "desiredRows": self.desired_rows
            }
        )
        await asyncio.sleep(0.3)
        
        # If rows still don't match, do iterative refinement
        if self.desired_rows and term_size and term_size['rows'] != self.desired_rows:
            for _ in range(3):
                term_size = await page.evaluate(
                    "desiredRows => refineTerminalRows(desiredRows)",
                    self.desired_rows
                )
                await asyncio.sleep(0.2)
                if term_size and term_size.get('done'):
                    break
        
        return term_size
    
    def _process_theme_commands(self, segment: Segment):
        """Extract and apply SetTheme commands from segment."""
        for cmd in segment.commands:
            if cmd.name == "SetTheme" and cmd.args:
                theme_name = cmd.args[0].lower().replace(" ", "-")
                if theme_name in THEMES:
                    self.theme = theme_name
    
    def _cleanup_ttyd(self):
        """Terminate ttyd subprocess cleanly."""
        if self._ttyd_process:
            self._ttyd_process.terminate()
            try:
                self._ttyd_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._ttyd_process.kill()
            self._ttyd_process = None
    
    def _finalize_video(self, output: Path, setup_duration: float):
        """Convert recorded webm to mp4, trimming setup frames."""
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            self._convert_to_mp4(latest, output, trim_start=setup_duration)
            latest.unlink()
    
    async def _record_async(self, segment: Segment, output: Path) -> dict[int, tuple[float, float]]:
        """Main async recording loop.
        
        Phases:
        1. Setup: Start ttyd, launch browser, initialize terminal
        2. Recording: Execute commands with timestamp tracking
        3. Cleanup: Close browser, stop ttyd, convert video
        """
        from playwright.async_api import async_playwright
        
        timestamps: dict[int, tuple[float, float]] = {}
        setup_duration = 0.0
        
        # Phase 1a: Process theme commands
        self._process_theme_commands(segment)
        
        # Phase 1b: Start ttyd
        port = _find_free_port()
        env = self._create_ttyd_env()
        self._ttyd_process = self._start_ttyd(port, env)
        await asyncio.sleep(0.5)  # Wait for ttyd to start
        
        try:
            async with async_playwright() as p:
                # Phase 1c: Launch browser with video recording
                browser = await p.chromium.launch()
                context = await browser.new_context(
                    viewport={"width": self.width, "height": self.height},
                    device_scale_factor=1,
                    record_video_dir=str(output.parent),
                    record_video_size={"width": self.width, "height": self.height},
                )
                page = await context.new_page()
                video_start_time = time.time()
                
                # Phase 1d: Connect to ttyd and wait for terminal
                await page.goto(f"http://localhost:{port}", wait_until="networkidle")
                await page.wait_for_selector(".xterm-screen", timeout=10000)
                await page.wait_for_function("() => window.term !== undefined", timeout=10000)
                await asyncio.sleep(0.3)
                
                # Phase 1e: Initialize terminal (theme, fonts, sizing)
                term_size = await self._initialize_terminal(page)
                await self._wait_for_terminal_ready(page, term_size)
                
                # Phase 1f: Clear terminal and finalize setup
                await page.keyboard.press("Control+l")
                await asyncio.sleep(0.5)
                
                if term_size and term_size.get('rows'):
                    self._vim_expander.set_terminal_rows(term_size['rows'])
                
                setup_duration = time.time() - video_start_time
                
                # Phase 2: Execute commands
                async def execute_cmd(cmd: Command):
                    await self._execute_command(page, cmd)
                
                timestamps = await execute_with_narration_timing(
                    commands=segment.commands,
                    timed_narrations=self._timed_narrations,
                    execute_fn=execute_cmd,
                )
                
                await asyncio.sleep(0.5)  # Final pause
                await context.close()
                await browser.close()
        finally:
            # Phase 3a: Cleanup ttyd
            self._cleanup_ttyd()
        
        # Phase 3b: Convert video
        self._finalize_video(output, setup_duration)
        
        return timestamps
    
    async def _send_keys(self, page, text: str, delay: float = None):
        """Send keystrokes to the terminal.
        
        Args:
            page: Playwright page object
            text: Text to type
            delay: Delay between keystrokes (defaults to self.typing_speed)
        """
        if delay is None:
            delay = self.typing_speed
        
        for char in text:
            await page.keyboard.type(char, delay=0)
            if delay > 0:
                await asyncio.sleep(delay)
    
    # Command handlers - each returns an awaitable
    async def _cmd_type(self, page, cmd: Command):
        if cmd.args:
            await self._send_keys(page, cmd.args[0])

    async def _cmd_enter(self, page, cmd: Command):
        await page.keyboard.press("Enter")
        await asyncio.sleep(0.3)

    async def _cmd_run(self, page, cmd: Command):
        if cmd.args:
            await self._send_keys(page, cmd.args[0])
            await page.keyboard.press("Enter")
            wait_time = parse_time(cmd.args[1]) if len(cmd.args) > 1 else 1.0
            await asyncio.sleep(wait_time)

    async def _cmd_sleep(self, page, cmd: Command):
        if cmd.args:
            await asyncio.sleep(parse_time(cmd.args[0]))

    async def _cmd_keypress(self, page, cmd: Command, key: str, delay: float = 0.1):
        """Generic key press handler."""
        await page.keyboard.press(key)
        await asyncio.sleep(delay)

    async def _cmd_backspace(self, page, cmd: Command):
        count = int(cmd.args[0]) if cmd.args else 1
        for _ in range(count):
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.05)

    def _build_command_handlers(self):
        """Build command dispatch table. O(1) lookup instead of O(N) elif chain."""
        return {
            "SetTheme": lambda page, cmd: asyncio.sleep(0),  # No-op, processed earlier
            "Type": self._cmd_type,
            "Enter": self._cmd_enter,
            "Run": self._cmd_run,
            "Sleep": self._cmd_sleep,
            "Ctrl+C": lambda page, cmd: self._cmd_keypress(page, cmd, "Control+c"),
            "Ctrl+D": lambda page, cmd: self._cmd_keypress(page, cmd, "Control+d"),
            "Ctrl+L": lambda page, cmd: self._cmd_keypress(page, cmd, "Control+l"),
            "Ctrl+Z": lambda page, cmd: self._cmd_keypress(page, cmd, "Control+z"),
            "Tab": lambda page, cmd: self._cmd_keypress(page, cmd, "Tab", 0.2),
            "Up": lambda page, cmd: self._cmd_keypress(page, cmd, "ArrowUp"),
            "Down": lambda page, cmd: self._cmd_keypress(page, cmd, "ArrowDown"),
            "Backspace": self._cmd_backspace,
            "Escape": lambda page, cmd: self._cmd_keypress(page, cmd, "Escape"),
            "Space": lambda page, cmd: self._cmd_keypress(page, cmd, "Space", 0.05),
            "Clear": lambda page, cmd: self._cmd_keypress(page, cmd, "Control+l"),
        }

    async def _execute_command(self, page, cmd: Command):
        """Execute a single command in the terminal.
        
        Uses dispatch table for O(1) command lookup instead of elif chain.
        
        Args:
            page: Playwright page object
            cmd: Command to execute
        """
        # Check for high-level vim commands first
        if self._vim_expander.is_vim_command(cmd.name):
            expanded = self._vim_expander.expand_command(cmd.name, cmd.args)
            await self._execute_vim_sequence(page, expanded)
            return
        
        # Dispatch table lookup
        handlers = self._build_command_handlers()
        handler = handlers.get(cmd.name)
        if handler:
            await handler(page, cmd)

    def _size_matches_expected(self, current: dict, expected: dict | None) -> bool:
        """Check if current size matches expected dimensions."""
        if not expected:
            return True
        expected_rows = expected.get('rows')
        expected_cols = expected.get('cols')
        if expected_rows and current['rows'] != expected_rows:
            return False
        if expected_cols and current['cols'] != expected_cols:
            return False
        return True

    def _size_is_stable(self, current: dict, last: dict | None) -> bool:
        """Check if size is stable (matches last check)."""
        if not last:
            return False
        return current['rows'] == last['rows'] and current['cols'] == last['cols']

    async def _get_terminal_size(self, page) -> dict | None:
        """Query terminal size via xterm.js API."""
        return await page.evaluate("""() => {
            if (!window.term) return null;
            return {
                rows: window.term.rows,
                cols: window.term.cols,
                bufferReady: window.term.buffer && window.term.buffer.active !== undefined
            };
        }""")

    async def _wait_for_terminal_ready(self, page, expected_size: dict | None,
                                       stable_checks: int = 3, check_interval: float = 0.3,
                                       max_wait: float = 5.0):
        """Wait for terminal to report stable dimensions before recording.
        
        Terminal is ready when it reports consistent rows/cols for
        `stable_checks` consecutive checks, matching expected_size if provided.
        """
        start_time = time.time()
        consecutive_matches = 0
        last_size = None
        
        while time.time() - start_time < max_wait:
            current_size = await self._get_terminal_size(page)
            
            if not current_size:
                await asyncio.sleep(check_interval)
                continue
            
            is_ready = (
                self._size_is_stable(current_size, last_size) and
                self._size_matches_expected(current_size, expected_size)
            )
            
            consecutive_matches = consecutive_matches + 1 if is_ready else 0
            if consecutive_matches >= stable_checks:
                return
            
            last_size = current_size
            await asyncio.sleep(check_interval)

    async def _execute_vim_sequence(self, page, commands: list[tuple[str, float]]):
        """Execute a sequence of vim keystrokes.
        
        Args:
            page: Playwright page object
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
                # Regular text - type it character by character for visibility
                await self._send_keys(page, keys, delay=0.02)
            
            if delay > 0:
                await asyncio.sleep(delay)
    
    def _convert_to_mp4(self, webm_path: Path, mp4_path: Path, trim_start: float = 0):
        """Convert webm to mp4 using FFmpeg, optionally trimming the start.
        
        Args:
            webm_path: Input webm file
            mp4_path: Output mp4 file
            trim_start: Seconds to trim from the beginning (for removing setup/resize frames)
        """
        cmd = ["ffmpeg", "-y"]
        
        # Add seek option to trim beginning (before input for fast seek)
        if trim_start > 0:
            cmd.extend(["-ss", f"{trim_start:.2f}"])
        
        cmd.extend([
            "-i", str(webm_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            str(mp4_path)
        ])
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {result.stderr}")
