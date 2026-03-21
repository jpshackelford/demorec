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
    
    async def _record_async(self, segment: Segment, output: Path):
        from playwright.async_api import async_playwright
        
        # Process SetTheme commands first
        for cmd in segment.commands:
            if cmd.name == "SetTheme" and cmd.args:
                theme_name = cmd.args[0].lower().replace(" ", "-")
                if theme_name in THEMES:
                    self.theme = theme_name
        
        # Find a free port for ttyd
        port = _find_free_port()
        
        # Start ttyd with a clean shell
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PS1"] = "$ "  # Simple prompt
        # Remove PROMPT_COMMAND to avoid unwanted prompt modifications
        env.pop("PROMPT_COMMAND", None)
        
        # Start ttyd
        self._ttyd_process = subprocess.Popen(
            [
                "ttyd",
                "--port", str(port),
                "--writable",  # Allow input
                "--once",  # Exit after one connection
                "/bin/bash", "--norc", "--noprofile"
            ],
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
                    device_scale_factor=2,
                    record_video_dir=str(output.parent),
                    record_video_size={"width": self.width, "height": self.height},
                )
                page = await context.new_page()
                
                # Navigate to ttyd
                await page.goto(f"http://localhost:{port}", wait_until="networkidle")
                
                # Wait for terminal to be ready (ttyd creates #terminal-container with xterm)
                await page.wait_for_selector(".xterm-screen", timeout=10000)
                await asyncio.sleep(1.0)  # Let terminal fully initialize
                
                # Execute commands
                for cmd in segment.commands:
                    await self._execute_command(page, cmd)
                
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
        
        # Convert video
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            self._convert_to_mp4(latest, output)
            latest.unlink()
    
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
        if cmd.name == "SetTheme":
            pass  # Processed earlier (ttyd has its own theming)
        
        elif cmd.name == "Type":
            if cmd.args:
                text = cmd.args[0]
                await self._send_keys(page, text)
        
        elif cmd.name == "Enter":
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.3)  # Wait for command to process
        
        elif cmd.name == "Run":
            # Type command and execute
            if cmd.args:
                command = cmd.args[0]
                await self._send_keys(page, command)
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
    
    def _convert_to_mp4(self, webm_path: Path, mp4_path: Path):
        """Convert webm to mp4 using FFmpeg."""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(webm_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            str(mp4_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {result.stderr}")
