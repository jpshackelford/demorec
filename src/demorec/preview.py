"""Preview runner for verifying terminal recordings at checkpoints.

Runs through a script, pausing at auto-detected checkpoints to verify
that expected content is visible on screen.
"""

import asyncio
import os
import subprocess
import shutil
import re
from dataclasses import dataclass
from pathlib import Path

from .stage import Checkpoint


@dataclass
class CheckpointResult:
    """Result of verifying a checkpoint."""
    checkpoint: Checkpoint
    passed: bool
    expected_lines: tuple[int, int] | None
    visible_lines: tuple[int, int] | None
    screenshot_path: Path | None
    error_message: str | None


@dataclass 
class PreviewResult:
    """Overall result of preview run."""
    total: int
    passed: int
    failed: int
    results: list[CheckpointResult]
    screenshot_dir: Path | None


class TerminalPreviewer:
    """Previews a terminal recording, verifying checkpoints."""
    
    def __init__(
        self,
        rows: int = 30,
        width: int = 1280,
        height: int = 720,
        screenshots: str = "on_error"  # "always", "never", "on_error"
    ):
        self.rows = rows
        self.width = width
        self.height = height
        self.screenshots = screenshots
        self._ttyd_process = None
    
    def preview(self, script_path: Path, segment, output_dir: Path | None = None) -> PreviewResult:
        """Run preview and return results."""
        return asyncio.run(self._preview_async(script_path, segment, output_dir))
    
    async def _preview_async(
        self, 
        script_path: Path, 
        segment, 
        output_dir: Path | None
    ) -> PreviewResult:
        from playwright.async_api import async_playwright
        
        # Detect checkpoints from parsed commands
        checkpoints = self._detect_checkpoints_from_commands(segment.commands)
        
        # Set up screenshot directory if needed
        screenshot_dir = None
        if self.screenshots != "never":
            screenshot_dir = output_dir or Path(".demorec_preview")
            screenshot_dir.mkdir(exist_ok=True)
        
        # Find ttyd (check multiple locations including ~/.local/bin)
        local_bin = str(Path.home() / ".local/bin")
        search_path = f"{local_bin}:{os.environ.get('PATH', '')}"
        
        ttyd_path = shutil.which("ttyd", path=search_path)
        if not ttyd_path:
            # Check common locations explicitly
            for path in ["/usr/local/bin/ttyd", f"{local_bin}/ttyd"]:
                if Path(path).exists():
                    ttyd_path = path
                    break
        
        if not ttyd_path:
            raise RuntimeError("ttyd not found. Install with: brew install ttyd")
        
        # Start ttyd on a random port with clean environment
        port = 7682
        
        # Critical: Remove OpenHands PS1JSON artifacts by clearing PROMPT_COMMAND
        # and setting a simple PS1
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PS1"] = "$ "  # Simple prompt
        env["PROMPT_COMMAND"] = ""  # Clear PROMPT_COMMAND that sets PS1JSON
        
        # Ensure PATH includes common binary locations (including vim)
        local_bin = str(Path.home() / ".local/bin")
        current_path = env.get("PATH", "")
        if local_bin not in current_path:
            env["PATH"] = f"{local_bin}:{current_path}"
        
        # Remove any other prompt-related variables that might interfere
        for key in list(env.keys()):
            if "PROMPT" in key and key != "PROMPT_COMMAND":
                del env[key]
        
        # Start ttyd with bash --norc --noprofile to avoid loading any shell configs
        self._ttyd_process = subprocess.Popen(
            [ttyd_path, "-p", str(port), "--writable", "--once", "/bin/bash", "--norc", "--noprofile"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        await asyncio.sleep(0.5)
        
        results: list[CheckpointResult] = []
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context(
                    viewport={"width": self.width, "height": self.height},
                )
                page = await context.new_page()
                
                await page.goto(f"http://localhost:{port}", wait_until="networkidle")
                await page.wait_for_selector(".xterm-screen", timeout=10000)
                await page.wait_for_function("() => window.term !== undefined", timeout=10000)
                await asyncio.sleep(0.3)
                
                # Set up terminal (same as recording)
                await self._setup_terminal(page)
                
                # Build checkpoint lookup by command index
                checkpoint_map: dict[int, Checkpoint] = {
                    cp.command_index: cp for cp in checkpoints
                }
                
                # Execute commands, pausing at checkpoints
                for cmd_idx, cmd in enumerate(segment.commands):
                    await self._execute_command(page, cmd)
                    
                    # Check if this is a checkpoint
                    if cmd_idx in checkpoint_map:
                        # Wait for vim to render the visual selection
                        await asyncio.sleep(0.5)
                        
                        cp = checkpoint_map[cmd_idx]
                        result = await self._verify_checkpoint(page, cp, screenshot_dir, len(results) + 1)
                        results.append(result)
                
                await context.close()
                await browser.close()
                
        finally:
            if self._ttyd_process:
                self._ttyd_process.terminate()
                try:
                    self._ttyd_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._ttyd_process.kill()
        
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        
        return PreviewResult(
            total=len(results),
            passed=passed,
            failed=failed,
            results=results,
            screenshot_dir=screenshot_dir if results else None
        )
    
    def _detect_checkpoints_from_commands(self, commands) -> list[Checkpoint]:
        """Detect checkpoints from parsed commands.
        
        Looks for visual selection patterns:
        - Type "NG" (goto line)
        - Type "V" (visual mode)
        - Type "NG" (extend selection)
        - ... eventually Escape
        
        Checkpoint fires right before Escape.
        """
        checkpoints = []
        
        in_visual_mode = False
        visual_start_line: int | None = None
        pending_goto: int | None = None
        last_goto_idx: int = 0
        
        for i, cmd in enumerate(commands):
            if cmd.name == "Type" and cmd.args:
                typed = cmd.args[0]
                
                # Detect goto (e.g., "6G", "27G")
                goto_match = re.match(r'^(\d+)G', typed)
                if goto_match:
                    pending_goto = int(goto_match.group(1))
                    last_goto_idx = i
                
                # Detect visual mode
                if typed in ("V", "v"):
                    in_visual_mode = True
                    visual_start_line = pending_goto
            
            elif cmd.name == "Escape":
                if in_visual_mode and visual_start_line and pending_goto:
                    start = min(visual_start_line, pending_goto)
                    end = max(visual_start_line, pending_goto)
                    
                    # Checkpoint is at the last goto before Escape (the selection end)
                    checkpoints.append(Checkpoint(
                        line_number=last_goto_idx,  # We use command index as line_number for simplicity
                        command_index=last_goto_idx,
                        event_type="visual_selection",
                        description=f"Visual selection: lines {start}-{end}",
                        expected_highlight=(start, end)
                    ))
                
                in_visual_mode = False
                visual_start_line = None
        
        return checkpoints
    
    async def _setup_terminal(self, page):
        """Set up terminal with proper sizing."""
        # Calculate desired rows and set up terminal
        await page.evaluate("""(config) => {
            if (!window.term) return null;
            
            const container = document.querySelector('.xterm');
            if (container) {
                container.style.width = '100vw';
                container.style.height = '100vh';
                container.style.position = 'fixed';
                container.style.top = '0';
                container.style.left = '0';
            }
            
            if (config.fontSize) {
                term.options.fontSize = config.fontSize;
            }
            if (config.fontFamily) {
                term.options.fontFamily = config.fontFamily;
            }
            
            term.fit();
            
            return { rows: term.rows, cols: term.cols };
        }""", {"fontSize": 14, "fontFamily": "Monaco, 'Courier New', monospace"})
        
        # Iteratively adjust font size to get desired rows
        for _ in range(10):
            term_size = await page.evaluate("""(desiredRows) => {
                if (!window.term) return null;
                
                const currentRows = term.rows;
                if (currentRows === desiredRows) {
                    return { rows: currentRows, done: true };
                }
                
                const ratio = currentRows / desiredRows;
                const currentFontSize = term.options.fontSize || 14;
                const newFontSize = Math.max(8, Math.min(32, Math.round(currentFontSize * ratio)));
                
                if (newFontSize !== currentFontSize) {
                    term.options.fontSize = newFontSize;
                    term.fit();
                }
                
                return { rows: term.rows, fontSize: newFontSize, done: term.rows === desiredRows };
            }""", self.rows)
            
            await asyncio.sleep(0.1)
            
            if term_size and term_size.get('done'):
                break
        
        # Clear terminal
        await page.keyboard.press("Control+l")
        await asyncio.sleep(0.3)
    
    async def _execute_command(self, page, cmd):
        """Execute a single command."""
        if cmd.name == "Type":
            text = cmd.args[0] if cmd.args else ""
            for char in text:
                await page.keyboard.type(char, delay=0)
                await asyncio.sleep(0.02)
        elif cmd.name == "Enter":
            await page.keyboard.press("Enter")
        elif cmd.name == "Escape":
            await page.keyboard.press("Escape")
        elif cmd.name == "Sleep":
            duration = self._parse_duration(cmd.args[0]) if cmd.args else 0.5
            await asyncio.sleep(duration)
        elif cmd.name == "Ctrl+l" or cmd.name == "Clear":
            await page.keyboard.press("Control+l")
        
        # Small delay between commands
        await asyncio.sleep(0.05)
    
    def _parse_duration(self, duration_str: str) -> float:
        """Parse duration string like '1s', '500ms', '0.5s'."""
        duration_str = duration_str.strip().lower()
        if duration_str.endswith("ms"):
            return float(duration_str[:-2]) / 1000
        elif duration_str.endswith("s"):
            return float(duration_str[:-1])
        else:
            return float(duration_str)
    
    async def _verify_checkpoint(
        self, 
        page, 
        checkpoint: Checkpoint, 
        screenshot_dir: Path | None,
        checkpoint_num: int
    ) -> CheckpointResult:
        """Verify a checkpoint and return result."""
        
        # Query the terminal buffer for visible content
        buffer_state = await page.evaluate("""() => {
            if (!window.term) return null;
            
            const term = window.term;
            const buffer = term.buffer.active;
            
            const visibleLines = [];
            for (let i = 0; i < term.rows; i++) {
                const line = buffer.getLine(buffer.viewportY + i);
                if (line) {
                    visibleLines.push(line.translateToString().trimEnd());
                }
            }
            
            return {
                rows: term.rows,
                cols: term.cols,
                viewportY: buffer.viewportY,
                visibleLines: visibleLines
            };
        }""")
        
        # Parse line numbers from visible content
        visible_line_range = self._extract_line_range(buffer_state.get('visibleLines', []))
        
        # Check if expected lines are visible
        expected = checkpoint.expected_highlight
        passed = True
        error_message = None
        
        if expected and visible_line_range:
            expected_start, expected_end = expected
            visible_start, visible_end = visible_line_range
            
            # Check if all expected lines are within visible range
            if expected_start < visible_start or expected_end > visible_end:
                passed = False
                if expected_start < visible_start:
                    error_message = f"Line {expected_start} not visible (viewport starts at {visible_start})"
                else:
                    error_message = f"Line {expected_end} not visible (viewport ends at {visible_end})"
        
        # Capture screenshot if needed
        screenshot_path = None
        should_screenshot = (
            self.screenshots == "always" or 
            (self.screenshots == "on_error" and not passed)
        )
        
        if should_screenshot and screenshot_dir:
            screenshot_path = screenshot_dir / f"checkpoint_{checkpoint_num}_{checkpoint.event_type}.png"
            await page.screenshot(path=str(screenshot_path))
        
        return CheckpointResult(
            checkpoint=checkpoint,
            passed=passed,
            expected_lines=expected,
            visible_lines=visible_line_range,
            screenshot_path=screenshot_path,
            error_message=error_message
        )
    
    def _extract_line_range(self, visible_lines: list[str]) -> tuple[int, int] | None:
        """Extract the range of line numbers visible on screen.
        
        Looks for vim line numbers at the start of lines (e.g., "  1 ", " 27 ").
        """
        line_numbers = []
        
        for line in visible_lines:
            # Match vim line number format: optional spaces, digits, space
            match = re.match(r'^\s*(\d+)\s', line)
            if match:
                line_numbers.append(int(match.group(1)))
        
        if line_numbers:
            return (min(line_numbers), max(line_numbers))
        
        return None
