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
    
    async def _record_async(self, segment: Segment, output: Path) -> dict[int, tuple[float, float]]:
        from playwright.async_api import async_playwright
        import time
        
        # Track command timestamps
        timestamps: dict[int, tuple[float, float]] = {}
        
        # Track when video recording starts vs when setup completes
        video_start_time = None
        setup_duration = 0.0
        
        # Process SetTheme commands first
        for cmd in segment.commands:
            if cmd.name == "SetTheme" and cmd.args:
                theme_name = cmd.args[0].lower().replace(" ", "-")
                if theme_name in THEMES:
                    self.theme = theme_name
        
        # Find a free port for ttyd
        port = _find_free_port()
        
        # Start ttyd with a clean shell environment
        # Critical: Remove OpenHands PS1JSON artifacts by clearing PROMPT_COMMAND
        # and setting a simple PS1
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PS1"] = "$ "  # Simple prompt
        env["PROMPT_COMMAND"] = ""  # Clear PROMPT_COMMAND that sets PS1JSON
        
        # Remove any other prompt-related variables that might interfere
        for key in list(env.keys()):
            if "PROMPT" in key and key != "PROMPT_COMMAND":
                del env[key]
        
        # Start ttyd - we'll configure xterm.js via JavaScript after load
        ttyd_cmd = [
            "ttyd",
            "--port", str(port),
            "--writable",  # Allow input
            "--once",  # Exit after one connection
            "/bin/bash", "--norc", "--noprofile"
        ]
        
        self._ttyd_process = subprocess.Popen(
            ttyd_cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        # Wait for ttyd to start
        await asyncio.sleep(0.5)
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context(
                    viewport={"width": self.width, "height": self.height},
                    device_scale_factor=1,  # Use 1:1 scale for accurate terminal sizing
                    record_video_dir=str(output.parent),
                    record_video_size={"width": self.width, "height": self.height},
                )
                page = await context.new_page()
                
                # Video recording starts now
                video_start_time = time.time()
                
                # Navigate to ttyd
                await page.goto(f"http://localhost:{port}", wait_until="networkidle")
                
                # Wait for terminal to be ready (ttyd creates window.term)
                await page.wait_for_selector(".xterm-screen", timeout=10000)
                await page.wait_for_function("() => window.term !== undefined", timeout=10000)
                await asyncio.sleep(0.3)  # Let terminal fully initialize
                
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
                    for _ in range(3):  # Max 3 iterations
                        term_size = await page.evaluate(
                            "desiredRows => refineTerminalRows(desiredRows)",
                            self.desired_rows
                        )
                        await asyncio.sleep(0.2)
                        
                        if term_size and term_size.get('done'):
                            break
                
                # Wait for terminal to report stable dimensions before proceeding
                await self._wait_for_terminal_ready(page, term_size)
                
                # Clear terminal for clean start (PTY is already synced via term.fit())
                await page.keyboard.press("Control+l")
                await asyncio.sleep(0.5)  # Wait for clear to render
                
                # Update vim expander with actual terminal rows
                if term_size and term_size.get('rows'):
                    self._vim_expander.set_terminal_rows(term_size['rows'])
                
                # Setup is complete - mark this time for video trimming
                setup_duration = time.time() - video_start_time
                
                # Store page for command execution
                self._page = page
                
                # Execute commands with shared timestamp tracking
                timestamps = await execute_with_narration_timing(
                    commands=segment.commands,
                    timed_narrations=self._timed_narrations,
                    execute_fn=self._execute_command,
                )
                
                # Final pause
                await asyncio.sleep(0.5)
                
                await context.close()
                await browser.close()
        finally:
            # Clean up ttyd
            if self._ttyd_process:
                self._ttyd_process.terminate()
                try:
                    self._ttyd_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._ttyd_process.kill()
        
        # Convert video, trimming the setup portion
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            self._convert_to_mp4(latest, output, trim_start=setup_duration)
            latest.unlink()
        
        return timestamps
    
    async def _send_keys(self, text: str, delay: float = None):
        """Send keystrokes to the terminal."""
        if delay is None:
            delay = self.typing_speed
        
        page = self._page
        for char in text:
            await page.keyboard.type(char, delay=0)
            if delay > 0:
                await asyncio.sleep(delay)
    
    async def _execute_command(self, cmd: Command):
        """Execute a command in the real PTY."""
        page = self._page
        
        # Check for high-level vim commands first
        if self._vim_expander.is_vim_command(cmd.name):
            expanded = self._vim_expander.expand_command(cmd.name, cmd.args)
            await self._execute_vim_sequence(expanded)
            return
        
        if cmd.name == "SetTheme":
            pass  # Processed earlier (ttyd has its own theming)
        
        elif cmd.name == "Type":
            if cmd.args:
                text = cmd.args[0]
                await self._send_keys(text)
        
        elif cmd.name == "Enter":
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.3)  # Wait for command to process
        
        elif cmd.name == "Run":
            # Type command and execute
            if cmd.args:
                command = cmd.args[0]
                await self._send_keys(command)
                await page.keyboard.press("Enter")
                
                # Wait for output
                wait_time = parse_time(cmd.args[1]) if len(cmd.args) > 1 else 1.0
                await asyncio.sleep(wait_time)
        
        elif cmd.name == "Sleep":
            if cmd.args:
                seconds = parse_time(cmd.args[0])
                await asyncio.sleep(seconds)
        
        elif cmd.name == "Ctrl+C":
            await page.keyboard.press("Control+c")
            await asyncio.sleep(0.1)
        
        elif cmd.name == "Ctrl+D":
            await page.keyboard.press("Control+d")
            await asyncio.sleep(0.1)
        
        elif cmd.name == "Ctrl+L":
            await page.keyboard.press("Control+l")
            await asyncio.sleep(0.1)
        
        elif cmd.name == "Ctrl+Z":
            await page.keyboard.press("Control+z")
            await asyncio.sleep(0.1)
        
        elif cmd.name == "Tab":
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.2)  # Wait for completion
        
        elif cmd.name == "Up":
            await page.keyboard.press("ArrowUp")
            await asyncio.sleep(0.1)
        
        elif cmd.name == "Down":
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(0.1)
        
        elif cmd.name == "Backspace":
            count = int(cmd.args[0]) if cmd.args else 1
            for _ in range(count):
                await page.keyboard.press("Backspace")
                await asyncio.sleep(0.05)
        
        elif cmd.name == "Escape":
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.1)
        
        elif cmd.name == "Space":
            await page.keyboard.press("Space")
            await asyncio.sleep(0.05)
        
        elif cmd.name == "Clear":
            await page.keyboard.press("Control+l")
            await asyncio.sleep(0.1)

    async def _wait_for_terminal_ready(self, page, expected_size: dict | None,
                                       stable_checks: int = 3, check_interval: float = 0.3,
                                       max_wait: float = 5.0):
        """Wait for terminal to report stable dimensions before recording.
        
        The terminal is considered "ready" when:
        1. It reports consistent rows/cols for several consecutive checks
        2. If expected_size is provided, dimensions match the expected values
        
        Args:
            page: Playwright page object
            expected_size: Expected {rows, cols} dict (optional)
            stable_checks: Number of consecutive matching checks required
            check_interval: Seconds between checks
            max_wait: Maximum seconds to wait before proceeding anyway
        """
        start_time = time.time()
        consecutive_matches = 0
        last_size = None
        expected_rows = expected_size.get('rows') if expected_size else None
        expected_cols = expected_size.get('cols') if expected_size else None
        
        while time.time() - start_time < max_wait:
            # Query terminal size via xterm.js API
            current_size = await page.evaluate("""() => {
                if (!window.term) return null;
                return {
                    rows: window.term.rows,
                    cols: window.term.cols,
                    bufferReady: window.term.buffer && window.term.buffer.active !== undefined
                };
            }""")
            
            if not current_size:
                await asyncio.sleep(check_interval)
                continue
            
            # Check if size matches expected (if specified)
            size_matches_expected = True
            if expected_rows and current_size['rows'] != expected_rows:
                size_matches_expected = False
            if expected_cols and current_size['cols'] != expected_cols:
                size_matches_expected = False
            
            # Check if size is stable (matches last check)
            size_is_stable = (
                last_size is not None and
                current_size['rows'] == last_size['rows'] and
                current_size['cols'] == last_size['cols']
            )
            
            if size_is_stable and size_matches_expected:
                consecutive_matches += 1
                if consecutive_matches >= stable_checks:
                    return  # Terminal is ready!
            else:
                consecutive_matches = 0
            
            last_size = current_size
            await asyncio.sleep(check_interval)

    async def _execute_vim_sequence(self, commands: list[tuple[str, float]]):
        """Execute a sequence of vim keystrokes.
        
        Args:
            commands: List of (keys, delay_after) tuples
                     Special keys: "ENTER", "ESCAPE", "TAB"
        """
        page = self._page
        for keys, delay in commands:
            if keys == "ENTER":
                await page.keyboard.press("Enter")
            elif keys == "ESCAPE":
                await page.keyboard.press("Escape")
            elif keys == "TAB":
                await page.keyboard.press("Tab")
            else:
                # Regular text - type it character by character for visibility
                await self._send_keys(keys, delay=0.02)
            
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
