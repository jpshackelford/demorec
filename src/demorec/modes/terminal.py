"""Terminal recording mode using xterm.js in Playwright."""

import asyncio
import subprocess
import tempfile
from pathlib import Path

from ..parser import Segment, Command, parse_time


# xterm.js terminal HTML template - use $placeholders to avoid CSS brace conflicts
TERMINAL_HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { 
            width: 100%; 
            height: 100%; 
            overflow: hidden;
            background: $background;
        }
        #terminal {
            width: 100%;
            height: 100%;
            padding: $padding;
        }
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
            allowTransparency: false,
            scrollback: 0,
        });
        
        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(document.getElementById('terminal'));
        fitAddon.fit();
        
        // Expose terminal to Playwright
        window.term = term;
        window.ready = true;
        
        // Write prompt
        term.write('$prompt');
    </script>
</body>
</html>
'''


def _render_terminal_html(background, padding, font_family, font_size, line_height, theme_json, prompt):
    """Render terminal HTML template with string substitution."""
    from string import Template
    t = Template(TERMINAL_HTML_TEMPLATE)
    # Escape single quotes in font_family for JS string
    font_family_escaped = font_family.replace("'", "\\'")
    return t.substitute(
        background=background,
        padding=f"{padding}px",
        font_family=font_family_escaped,
        font_size=font_size,
        line_height=line_height,
        theme_json=theme_json,
        prompt=prompt,
    )

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
    
    def record(self, segment: Segment, output: Path):
        """Record a terminal segment to video."""
        # Ensure absolute path for Playwright video recording
        output = output.absolute()
        asyncio.run(self._record_async(segment, output))
    
    async def _record_async(self, segment: Segment, output: Path):
        from playwright.async_api import async_playwright
        
        # Process SetTheme commands first
        for cmd in segment.commands:
            if cmd.name == "SetTheme" and cmd.args:
                theme_name = cmd.args[0].lower().replace(" ", "-")
                if theme_name in THEMES:
                    self.theme = theme_name
        
        # Generate HTML
        theme_data = THEMES.get(self.theme, THEMES["dracula"])
        import json
        html_content = _render_terminal_html(
            background=theme_data["background"],
            padding=self.padding,
            font_family=self.font_family,
            font_size=self.font_size,
            line_height=self.line_height,
            theme_json=json.dumps(theme_data),
            prompt=self.prompt,
        )
        
        # Write HTML to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(html_content)
            html_path = Path(f.name)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            # Enable video recording via context
            context = await browser.new_context(
                viewport={"width": self.width, "height": self.height},
                device_scale_factor=2,
                record_video_dir=str(output.parent),
                record_video_size={"width": self.width, "height": self.height},
            )
            page = await context.new_page()
            
            # Load terminal and wait for xterm.js to initialize
            await page.goto(f"file://{html_path}", wait_until="load")
            # Wait for CDN scripts to load and execute
            await page.wait_for_function("typeof Terminal === 'function'", timeout=10000)
            await page.wait_for_function("window.ready === true", timeout=10000)
            
            # Execute commands
            for cmd in segment.commands:
                await self._execute_command(page, cmd)
            
            # Close context to finalize video
            await context.close()
            await browser.close()
        
        # Playwright saves video with random name - find and rename it
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            self._convert_to_mp4(latest, output)
            latest.unlink()
        
        # Cleanup
        html_path.unlink()
    
    async def _execute_command(self, page, cmd: Command):
        """Execute a single terminal command."""
        if cmd.name == "SetTheme":
            # Already processed
            pass
        
        elif cmd.name == "Type":
            if cmd.args:
                text = cmd.args[0]
                # Type character by character with delay
                for char in text:
                    await page.evaluate(f"term.write({repr(char)})")
                    await asyncio.sleep(0.05)  # 50ms per char
        
        elif cmd.name == "Enter":
            await page.evaluate("term.write('\\r\\n')")
            await asyncio.sleep(0.1)
            # Write new prompt
            await page.evaluate(f"term.write({repr(self.prompt)})")
        
        elif cmd.name == "Sleep":
            if cmd.args:
                seconds = parse_time(cmd.args[0])
                await asyncio.sleep(seconds)
        
        elif cmd.name.startswith("Ctrl+"):
            key = cmd.name[5:].upper()
            # Map to control character
            ctrl_map = {
                "C": "\\x03",
                "D": "\\x04", 
                "Z": "\\x1a",
                "L": "\\x0c",
            }
            if key in ctrl_map:
                await page.evaluate(f"term.write('{ctrl_map[key]}')")
                await asyncio.sleep(0.1)
        
        elif cmd.name == "Backspace":
            count = int(cmd.args[0]) if cmd.args else 1
            for _ in range(count):
                await page.evaluate("term.write('\\b \\b')")
                await asyncio.sleep(0.05)
        
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
