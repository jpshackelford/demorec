"""Browser recording mode using Playwright."""

import asyncio
import subprocess
import time
from pathlib import Path

from ..parser import Segment, Command, parse_time


class BrowserRecorder:
    """Records browser sessions using Playwright."""
    
    def __init__(self, width: int = 1280, height: int = 720, framerate: int = 30):
        self.width = width
        self.height = height
        self.framerate = framerate
        self._timed_narrations = {}
    
    def record(self, segment: Segment, output: Path, timed_narrations: dict = None) -> dict[int, tuple[float, float]]:
        """Record a browser segment to video.
        
        Args:
            segment: The segment to record
            output: Output video file path
            timed_narrations: Dict mapping cmd_index to TimedNarration objects
            
        Returns:
            Dict mapping command index to (start_time, end_time) in seconds
        """
        output = output.absolute()
        self._timed_narrations = timed_narrations or {}
        return asyncio.run(self._record_async(segment, output))
    
    async def _record_async(self, segment: Segment, output: Path) -> dict[int, tuple[float, float]]:
        from playwright.async_api import async_playwright
        
        # Track command timestamps
        timestamps: dict[int, tuple[float, float]] = {}
        
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={"width": self.width, "height": self.height},
                record_video_dir=str(output.parent),
                record_video_size={"width": self.width, "height": self.height},
            )
            page = await context.new_page()
            
            # Mark recording start time
            recording_start = time.time()
            
            # Execute commands with timestamp tracking
            for cmd_idx, cmd in enumerate(segment.commands):
                # Check if this command has narration
                narration = self._timed_narrations.get(cmd_idx)
                
                # Handle "before" narration - add delay before command
                if narration and narration.mode == "before":
                    await asyncio.sleep(narration.duration)
                
                # Record command start time
                cmd_start = time.time() - recording_start
                
                # Execute the command
                await self._execute_command(page, cmd)
                
                # Record command end time
                cmd_end = time.time() - recording_start
                timestamps[cmd_idx] = (cmd_start, cmd_end)
                
                # Handle "after" narration - add delay after command
                if narration and narration.mode == "after":
                    await asyncio.sleep(narration.duration)
            
            # Close to finalize video
            await context.close()
            await browser.close()
        
        # Playwright saves video with random name - find and rename it
        video_files = list(output.parent.glob("*.webm"))
        if video_files:
            latest = max(video_files, key=lambda f: f.stat().st_mtime)
            self._convert_to_mp4(latest, output)
            latest.unlink()
        
        return timestamps
    
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
