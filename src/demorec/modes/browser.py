"""Browser recording mode using Playwright."""

import asyncio
import subprocess
from pathlib import Path

from ..parser import Segment, Command, parse_time


class BrowserRecorder:
    """Records browser sessions using Playwright."""
    
    def __init__(self, width: int = 1280, height: int = 720, framerate: int = 30):
        self.width = width
        self.height = height
        self.framerate = framerate
    
    def record(self, segment: Segment, output: Path):
        """Record a browser segment to video."""
        # Ensure absolute path for Playwright video recording
        output = output.absolute()
        asyncio.run(self._record_async(segment, output))
    
    async def _record_async(self, segment: Segment, output: Path):
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={"width": self.width, "height": self.height},
                record_video_dir=str(output.parent),
                record_video_size={"width": self.width, "height": self.height},
            )
            page = await context.new_page()
            
            # Execute commands
            for cmd in segment.commands:
                await self._execute_command(page, cmd)
            
            # Close to finalize video
            await context.close()
            await browser.close()
        
        # Playwright saves video with random name - find and rename it
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            self._convert_to_mp4(latest, output)
            latest.unlink()
    
    async def _execute_command(self, page, cmd: Command):
        """Execute a single browser command."""
        
        if cmd.name == "Navigate":
            if cmd.args:
                url = cmd.args[0]
                await page.goto(url, wait_until="networkidle")
        
        elif cmd.name == "Click":
            if cmd.args:
                selector = cmd.args[0]
                await page.click(selector)
        
        elif cmd.name == "Type":
            if len(cmd.args) >= 2:
                selector = cmd.args[0]
                text = cmd.args[1]
                await page.type(selector, text, delay=50)
            elif len(cmd.args) == 1:
                # Type without selector - use keyboard
                text = cmd.args[0]
                await page.keyboard.type(text, delay=50)
        
        elif cmd.name == "Fill":
            if len(cmd.args) >= 2:
                selector = cmd.args[0]
                text = cmd.args[1]
                await page.fill(selector, text)
        
        elif cmd.name == "Press":
            if cmd.args:
                key = cmd.args[0]
                await page.keyboard.press(key)
        
        elif cmd.name == "Sleep":
            if cmd.args:
                seconds = parse_time(cmd.args[0])
                await asyncio.sleep(seconds)
        
        elif cmd.name == "Wait":
            if cmd.args:
                selector = cmd.args[0]
                await page.wait_for_selector(selector)
        
        elif cmd.name == "Scroll":
            direction = cmd.args[0] if cmd.args else "down"
            amount = int(cmd.args[1]) if len(cmd.args) > 1 else 300
            if direction == "down":
                await page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await page.evaluate(f"window.scrollBy(0, -{amount})")
            await asyncio.sleep(0.3)  # Smooth scroll delay
        
        elif cmd.name == "Hover":
            if cmd.args:
                selector = cmd.args[0]
                await page.hover(selector)
        
        elif cmd.name == "Highlight":
            if cmd.args:
                selector = cmd.args[0]
                await page.evaluate(f'''
                    document.querySelector({repr(selector)}).style.outline = "3px solid red";
                ''')
        
        elif cmd.name == "Unhighlight":
            if cmd.args:
                selector = cmd.args[0]
                await page.evaluate(f'''
                    document.querySelector({repr(selector)}).style.outline = "";
                ''')
        
        elif cmd.name == "Screenshot":
            filename = cmd.args[0] if cmd.args else "screenshot.png"
            await page.screenshot(path=filename)
    
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
