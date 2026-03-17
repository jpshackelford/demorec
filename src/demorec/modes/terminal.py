"""Terminal recording mode using xterm.js with real command execution."""

import asyncio
import subprocess
import tempfile
import shlex
from pathlib import Path

from ..parser import Segment, Command, parse_time

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
    """Records terminal sessions using xterm.js in a headless browser."""
    
    def __init__(self, width: int = 1280, height: int = 720, framerate: int = 30):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.theme = "dracula"
        self.font_family = "Monaco, 'Cascadia Code', 'Fira Code', monospace"
        self.font_size = 16
        self.line_height = 1.2
        self.padding = 20
        self.prompt = "$ "
        self._current_line = ""  # Track what's being typed for Type+Enter
    
    def record(self, segment: Segment, output: Path):
        """Record a terminal segment to video with real command execution."""
        output = output.absolute()
        asyncio.run(self._record_async(segment, output))
    
    async def _record_async(self, segment: Segment, output: Path):
        from playwright.async_api import async_playwright
        import json
        
        # Process SetTheme commands first
        for cmd in segment.commands:
            if cmd.name == "SetTheme" and cmd.args:
                theme_name = cmd.args[0].lower().replace(" ", "-")
                if theme_name in THEMES:
                    self.theme = theme_name
        
        theme_data = THEMES.get(self.theme, THEMES["dracula"])
        
        # Generate HTML with xterm.js
        html_content = self._generate_html(theme_data)
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(html_content)
            html_path = Path(f.name)
        
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
                
                # Load terminal
                await page.goto(f"file://{html_path}", wait_until="load")
                await page.wait_for_function("typeof Terminal === 'function'", timeout=10000)
                await page.wait_for_function("window.ready === true", timeout=10000)
                
                # Execute commands
                for cmd in segment.commands:
                    await self._execute_command(page, cmd)
                
                # Final pause
                await asyncio.sleep(0.5)
                
                await context.close()
                await browser.close()
        finally:
            html_path.unlink()
        
        # Convert video
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            self._convert_to_mp4(latest, output)
            latest.unlink()
    
    def _generate_html(self, theme: dict) -> str:
        """Generate xterm.js HTML."""
        import json
        from string import Template
        
        template = Template('''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { 
            width: 100%; height: 100%; overflow: hidden;
            background: $background;
        }
        #terminal { width: 100%; height: 100%; padding: ${padding}px; }
        .xterm-viewport::-webkit-scrollbar { display: none; }
    </style>
</head>
<body>
    <div id="terminal"></div>
    <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"></script>
    <script>
        const term = new Terminal({
            fontFamily: '$font_family',
            fontSize: $font_size,
            lineHeight: $line_height,
            cursorBlink: true,
            cursorStyle: 'block',
            theme: $theme_json,
            scrollback: 1000,
        });
        
        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(document.getElementById('terminal'));
        fitAddon.fit();
        
        window.term = term;
        window.ready = true;
        
        // Show initial prompt
        term.write('$prompt');
    </script>
</body>
</html>
''')
        return template.substitute(
            background=theme["background"],
            padding=self.padding,
            font_family=self.font_family.replace("'", "\\'"),
            font_size=self.font_size,
            line_height=self.line_height,
            theme_json=json.dumps(theme),
            prompt=self.prompt,
        )
    
    async def _execute_command(self, page, cmd: Command):
        """Execute a command - runs for real and shows output."""
        if cmd.name == "SetTheme":
            pass  # Already processed
        
        elif cmd.name == "Type":
            if cmd.args:
                text = cmd.args[0]
                self._current_line += text  # Track what's typed
                # Type character by character with realistic delay
                for char in text:
                    escaped = repr(char)
                    await page.evaluate(f"term.write({escaped})")
                    await asyncio.sleep(0.05)
        
        elif cmd.name == "Enter":
            # Execute whatever was typed
            command = self._current_line.strip()
            self._current_line = ""  # Reset
            
            await page.evaluate("term.write('\\r\\n')")
            await asyncio.sleep(0.1)
            
            if command:
                # Actually execute the command
                try:
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=Path.home(),
                    )
                    output = result.stdout + result.stderr
                except subprocess.TimeoutExpired:
                    output = "[Command timed out]\n"
                except Exception as e:
                    output = f"[Error: {e}]\n"
                
                # Display the real output
                if output:
                    for line in output.split('\n'):
                        if line:
                            safe_line = line.replace('\\', '\\\\').replace("'", "\\'").replace('\r', '')
                            await page.evaluate(f"term.write('{safe_line}')")
                        await page.evaluate("term.write('\\r\\n')")
                        await asyncio.sleep(0.02)
            
            # Show prompt
            await page.evaluate(f"term.write({repr(self.prompt)})")
        
        elif cmd.name == "Run":
            # Type command, execute it, show real output
            if cmd.args:
                command = cmd.args[0]
                
                # Type the command visually
                for char in command:
                    await page.evaluate(f"term.write({repr(char)})")
                    await asyncio.sleep(0.04)
                
                # Press enter
                await page.evaluate("term.write('\\r\\n')")
                await asyncio.sleep(0.1)
                
                # Actually execute the command and capture output
                try:
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=Path.home(),
                    )
                    output = result.stdout + result.stderr
                except subprocess.TimeoutExpired:
                    output = "[Command timed out]\n"
                except Exception as e:
                    output = f"[Error: {e}]\n"
                
                # Display the real output
                if output:
                    # Convert output to terminal-safe format
                    for line in output.split('\n'):
                        if line:
                            # Escape special characters for JS
                            safe_line = line.replace('\\', '\\\\').replace("'", "\\'").replace('\r', '')
                            await page.evaluate(f"term.write('{safe_line}')")
                        await page.evaluate("term.write('\\r\\n')")
                        await asyncio.sleep(0.02)  # Small delay between lines
                
                # Show prompt
                await page.evaluate(f"term.write({repr(self.prompt)})")
                
                # Wait time for viewing
                wait_time = float(cmd.args[1]) if len(cmd.args) > 1 else 0.5
                await asyncio.sleep(wait_time)
        
        elif cmd.name == "Exec":
            # Execute without typing (instant)
            if cmd.args:
                command = cmd.args[0]
                try:
                    result = subprocess.run(
                        command, shell=True, capture_output=True, text=True, timeout=30
                    )
                    output = result.stdout + result.stderr
                except Exception as e:
                    output = f"[Error: {e}]\n"
                
                if output:
                    for line in output.split('\n'):
                        if line:
                            safe_line = line.replace('\\', '\\\\').replace("'", "\\'")
                            await page.evaluate(f"term.write('{safe_line}')")
                        await page.evaluate("term.write('\\r\\n')")
                
                await page.evaluate(f"term.write({repr(self.prompt)})")
        
        elif cmd.name == "Output":
            # Show text as if it were command output (for scripted demos)
            if cmd.args:
                text = cmd.args[0]
                for line in text.split('\n'):
                    safe_line = line.replace('\\', '\\\\').replace("'", "\\'")
                    await page.evaluate(f"term.write('{safe_line}\\r\\n')")
                    await asyncio.sleep(0.02)
        
        elif cmd.name == "Sleep":
            if cmd.args:
                seconds = parse_time(cmd.args[0])
                await asyncio.sleep(seconds)
        
        elif cmd.name == "Clear":
            await page.evaluate("term.clear()")
            await page.evaluate(f"term.write({repr(self.prompt)})")
    
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
