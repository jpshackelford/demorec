"""Preview runner for verifying terminal recordings at checkpoints.

Runs through a script, pausing at auto-detected checkpoints to verify
that expected content is visible on screen. Also supports frame-by-frame
capture for AI debugging and verification.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .stage import Checkpoint
from .ttyd import find_ttyd, start_ttyd, stop_ttyd
from .xterm import fit_to_rows, get_buffer_state, setup_container


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
    frame_count: int = 0
    frames_dir: Path | None = None


class TerminalPreviewer:
    """Previews a terminal recording, verifying checkpoints."""

    def __init__(
        self,
        rows: int = 30,
        width: int = 1280,
        height: int = 720,
        screenshots: str = "on_error",
        capture_frames: bool = False,
    ):
        self.rows = rows
        self.width = width
        self.height = height
        self.screenshots = screenshots
        self.capture_frames = capture_frames
        self._ttyd_process = None
        self._frame_counter = 0
        self._start_time: float | None = None
        self._frames_dir: Path | None = None

    def preview(self, script_path: Path, segment, output_dir: Path | None = None) -> PreviewResult:
        """Run preview and return results."""
        return asyncio.run(self._preview_async(script_path, segment, output_dir))

    async def _preview_async(
        self, script_path: Path, segment, output_dir: Path | None
    ) -> PreviewResult:
        checkpoints = self._detect_checkpoints_from_commands(segment.commands)
        screenshot_dir = self._setup_screenshot_dir(output_dir)
        self._setup_frames_dir(output_dir)

        find_ttyd()  # Validate ttyd exists (raises if not)
        port = 7682

        self._ttyd_process = start_ttyd(port)
        await asyncio.sleep(0.5)

        try:
            results = await self._run_browser_session(port, segment, checkpoints, screenshot_dir)
        finally:
            stop_ttyd(self._ttyd_process)

        return self._build_preview_result(results, screenshot_dir)

    def _setup_frames_dir(self, output_dir: Path | None):
        """Set up frames directory if frame capture is enabled."""
        if not self.capture_frames or not output_dir:
            self._frames_dir = None
            return
        self._frames_dir = output_dir
        self._frames_dir.mkdir(parents=True, exist_ok=True)
        self._frame_counter = 0
        self._start_time = None

    def _setup_screenshot_dir(self, output_dir: Path | None) -> Path | None:
        """Set up screenshot directory if needed."""
        if self.screenshots == "never":
            return None
        screenshot_dir = output_dir or Path(".demorec_preview")
        screenshot_dir.mkdir(exist_ok=True)
        return screenshot_dir

    def _build_preview_result(
        self, results: list[CheckpointResult], screenshot_dir: Path | None
    ) -> PreviewResult:
        """Build final PreviewResult from checkpoint results."""
        passed = sum(1 for r in results if r.passed)
        return PreviewResult(
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=results,
            screenshot_dir=screenshot_dir if results else None,
            frame_count=self._frame_counter,
            frames_dir=self._frames_dir,
        )

    async def _run_browser_session(
        self, port: int, segment, checkpoints: list[Checkpoint], screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Run the browser session and execute commands."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await self._setup_browser_page(browser, port)
            await self._setup_terminal(page)
            results = await self._run_commands(page, segment, checkpoints, screenshot_dir)
            await browser.close()
        return results

    async def _run_commands(
        self, page, segment, checkpoints: list[Checkpoint], screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Execute commands and verify checkpoints."""
        results: list[CheckpointResult] = []
        checkpoint_map = {cp.command_index: cp for cp in checkpoints}
        await self._init_frame_capture(page)

        for cmd_idx, cmd in enumerate(segment.commands):
            await self._execute_command(page, cmd)
            await self._maybe_capture_frame(page)
            result = await self._maybe_verify_checkpoint(
                page, cmd_idx, checkpoint_map, screenshot_dir, len(results)
            )
            if result:
                results.append(result)
        return results

    async def _init_frame_capture(self, page):
        """Initialize timing and capture initial frame if enabled."""
        if self.capture_frames and self._frames_dir:
            self._start_time = time.time()
            await self._capture_terminal_frame(page)

    async def _maybe_capture_frame(self, page):
        """Capture frame after command if enabled."""
        if self.capture_frames and self._frames_dir:
            await asyncio.sleep(0.05)
            await self._capture_terminal_frame(page)

    async def _maybe_verify_checkpoint(
        self, page, cmd_idx: int, checkpoint_map: dict, screenshot_dir: Path | None, count: int
    ) -> CheckpointResult | None:
        """Verify checkpoint if current command index matches."""
        if cmd_idx not in checkpoint_map:
            return None
        await asyncio.sleep(0.5)
        cp = checkpoint_map[cmd_idx]
        return await self._verify_checkpoint(page, cp, screenshot_dir, count + 1)

    async def _capture_terminal_frame(self, page) -> Path | None:
        """Capture a terminal frame as a text file.

        Saves the terminal buffer state to a .txt file with naming:
        frame_{NNNN}_{SSS.ss}.txt
        """
        if not self._frames_dir or self._start_time is None:
            return None

        self._frame_counter += 1
        elapsed = time.time() - self._start_time

        # Format: frame_0001_000.00.txt
        filename = f"frame_{self._frame_counter:04d}_{elapsed:06.2f}.txt"
        filepath = self._frames_dir / filename

        # Get terminal buffer state
        buffer_state = await get_buffer_state(page)
        if buffer_state and buffer_state.visible_lines:
            content = "\n".join(buffer_state.visible_lines)
            filepath.write_text(content)
            return filepath

        return None

    async def _setup_browser_page(self, browser, port: int):
        """Set up browser page and wait for terminal."""
        context = await browser.new_context(
            viewport={"width": self.width, "height": self.height},
        )
        page = await context.new_page()

        await page.goto(f"http://localhost:{port}", wait_until="networkidle")
        await page.wait_for_selector(".xterm-screen", timeout=10000)
        await page.wait_for_function("() => window.term !== undefined", timeout=10000)
        await asyncio.sleep(0.3)

        return page

    def _detect_checkpoints_from_commands(self, commands) -> list[Checkpoint]:
        """Detect checkpoints from visual selection patterns in commands."""
        checkpoints = []
        state = {"in_visual": False, "visual_start": None, "goto": None, "goto_idx": 0}

        for i, cmd in enumerate(commands):
            if cmd.name == "Type" and cmd.args:
                self._process_type_cmd(cmd.args[0], i, state)
            elif cmd.name == "Escape":
                checkpoint = self._process_escape(state)
                if checkpoint:
                    checkpoints.append(checkpoint)

        return checkpoints

    def _process_type_cmd(self, typed: str, idx: int, state: dict):
        """Process a Type command for goto/visual patterns."""
        goto_match = re.match(r"^(\d+)G", typed)
        if goto_match:
            state["goto"] = int(goto_match.group(1))
            state["goto_idx"] = idx

        if typed in ("V", "v"):
            state["in_visual"] = True
            state["visual_start"] = state["goto"]

    def _process_escape(self, state: dict) -> Checkpoint | None:
        """Process Escape command and create checkpoint if in visual mode."""
        if not (state["in_visual"] and state["visual_start"] and state["goto"]):
            self._clear_visual_state(state)
            return None

        checkpoint = self._create_visual_checkpoint(state)
        self._clear_visual_state(state)
        return checkpoint

    def _create_visual_checkpoint(self, state: dict) -> Checkpoint:
        """Create checkpoint for visual selection."""
        vs, gt = state["visual_start"], state["goto"]
        start, end = min(vs, gt), max(vs, gt)
        return Checkpoint(
            line_number=state["goto_idx"],
            command_index=state["goto_idx"],
            event_type="visual_selection",
            description=f"Visual selection: lines {start}-{end}",
            expected_highlight=(start, end),
        )

    def _clear_visual_state(self, state: dict):
        """Clear visual mode state."""
        state["in_visual"], state["visual_start"] = False, None

    async def _setup_terminal(self, page):
        """Set up terminal with proper sizing using xterm module."""
        await setup_container(page)
        await fit_to_rows(page, self.rows, max_iterations=10, delay=0.1)

        # Clear terminal
        await page.keyboard.press("Control+l")
        await asyncio.sleep(0.3)

    async def _execute_command(self, page, cmd):
        """Execute a single command."""
        await self._dispatch_command(page, cmd)
        await asyncio.sleep(0.05)

    async def _dispatch_command(self, page, cmd):
        """Dispatch command to appropriate handler."""
        if cmd.name == "Type":
            await self._type_text(page, cmd.args[0] if cmd.args else "")
        elif cmd.name == "Enter":
            await page.keyboard.press("Enter")
        elif cmd.name == "Escape":
            await page.keyboard.press("Escape")
        elif cmd.name == "Sleep":
            await asyncio.sleep(self._parse_duration(cmd.args[0]) if cmd.args else 0.5)
        elif cmd.name in ("Ctrl+l", "Clear"):
            await page.keyboard.press("Control+l")

    async def _type_text(self, page, text: str):
        """Type text character by character."""
        for char in text:
            await page.keyboard.type(char, delay=0)
            await asyncio.sleep(0.02)

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
        self, page, checkpoint: Checkpoint, screenshot_dir: Path | None, checkpoint_num: int
    ) -> CheckpointResult:
        """Verify a checkpoint and return result."""
        buffer_state = await get_buffer_state(page)
        visible_range = self._extract_line_range(buffer_state.visible_lines if buffer_state else [])
        passed, error = self._check_visibility(checkpoint.expected_highlight, visible_range)
        screenshot = await self._maybe_screenshot(
            page, screenshot_dir, checkpoint_num, checkpoint.event_type, passed
        )
        return self._build_result(checkpoint, passed, visible_range, screenshot, error)

    def _build_result(
        self,
        cp: Checkpoint,
        passed: bool,
        visible: tuple,
        screenshot: Path | None,
        error: str | None,
    ) -> CheckpointResult:
        """Build checkpoint result."""
        return CheckpointResult(
            checkpoint=cp,
            passed=passed,
            expected_lines=cp.expected_highlight,
            visible_lines=visible,
            screenshot_path=screenshot,
            error_message=error,
        )

    def _check_visibility(
        self, expected: tuple[int, int] | None, visible: tuple[int, int] | None
    ) -> tuple[bool, str | None]:
        """Check if expected lines are visible."""
        if not expected or not visible:
            return True, None

        expected_start, expected_end = expected
        visible_start, visible_end = visible

        if expected_start < visible_start:
            return False, f"Line {expected_start} not visible (viewport starts at {visible_start})"
        if expected_end > visible_end:
            return False, f"Line {expected_end} not visible (viewport ends at {visible_end})"

        return True, None

    async def _maybe_screenshot(
        self, page, screenshot_dir: Path | None, checkpoint_num: int, event_type: str, passed: bool
    ) -> Path | None:
        """Capture screenshot if needed."""
        should_screenshot = self.screenshots == "always" or (
            self.screenshots == "on_error" and not passed
        )

        if not should_screenshot or not screenshot_dir:
            return None

        filename = f"checkpoint_{checkpoint_num}_{event_type}.png"
        screenshot_path = screenshot_dir / filename
        await page.screenshot(path=str(screenshot_path))
        return screenshot_path

    def _extract_line_range(self, visible_lines: list[str]) -> tuple[int, int] | None:
        """Extract the range of line numbers visible on screen.

        Looks for vim line numbers at the start of lines (e.g., "  1 ", " 27 ").
        """
        line_numbers = []

        for line in visible_lines:
            # Match vim line number format: optional spaces, digits, space
            match = re.match(r"^\s*(\d+)\s", line)
            if match:
                line_numbers.append(int(match.group(1)))

        if line_numbers:
            return (min(line_numbers), max(line_numbers))

        return None


class ScriptPreviewer:
    """Previews a script with multiple segments (terminal and browser).

    Provides frame-by-frame capture for debugging and verification.
    Maintains continuous frame numbering across mode switches.
    """

    def __init__(
        self,
        rows: int = 30,
        width: int = 1280,
        height: int = 720,
        screenshots: str = "on_error",
        capture_frames: bool = False,
    ):
        self.rows = rows
        self.width = width
        self.height = height
        self.screenshots = screenshots
        self.capture_frames = capture_frames
        self._frame_counter = 0
        self._start_time: float | None = None
        self._frames_dir: Path | None = None
        self._ttyd_process = None

    def preview(
        self, script_path: Path, segments: list, output_dir: Path | None = None
    ) -> PreviewResult:
        """Run preview across all segments and return results."""
        return asyncio.run(self._preview_async(script_path, segments, output_dir))

    async def _preview_async(
        self, script_path: Path, segments: list, output_dir: Path | None
    ) -> PreviewResult:
        """Async preview implementation supporting terminal and browser modes."""
        self._setup_frames_dir(output_dir)
        screenshot_dir = self._setup_screenshot_dir(output_dir)
        self._init_start_time()

        all_results = await self._process_all_segments(segments, screenshot_dir)
        return self._build_preview_result(all_results, screenshot_dir)

    def _init_start_time(self):
        """Initialize start time for frame capture if enabled."""
        if self.capture_frames and self._frames_dir:
            self._start_time = time.time()

    async def _process_all_segments(
        self, segments: list, screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Process all segments and collect results."""
        all_results: list[CheckpointResult] = []
        for segment in segments:
            results = await self._preview_segment(segment, screenshot_dir)
            all_results.extend(results)
        return all_results

    async def _preview_segment(
        self, segment, screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Preview a single segment based on its mode."""
        if segment.mode == "terminal":
            return await self._preview_terminal_segment(segment, screenshot_dir)
        elif segment.mode == "browser":
            return await self._preview_browser_segment(segment, screenshot_dir)
        return []

    def _setup_frames_dir(self, output_dir: Path | None):
        """Set up frames directory if frame capture is enabled."""
        if not self.capture_frames or not output_dir:
            self._frames_dir = None
            return
        self._frames_dir = output_dir
        self._frames_dir.mkdir(parents=True, exist_ok=True)
        self._frame_counter = 0
        self._start_time = None

    def _setup_screenshot_dir(self, output_dir: Path | None) -> Path | None:
        """Set up screenshot directory if needed."""
        if self.screenshots == "never":
            return None
        screenshot_dir = output_dir or Path(".demorec_preview")
        screenshot_dir.mkdir(exist_ok=True)
        return screenshot_dir

    def _build_preview_result(
        self, results: list[CheckpointResult], screenshot_dir: Path | None
    ) -> PreviewResult:
        """Build final PreviewResult from checkpoint results."""
        passed = sum(1 for r in results if r.passed)
        return PreviewResult(
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=results,
            screenshot_dir=screenshot_dir if results else None,
            frame_count=self._frame_counter,
            frames_dir=self._frames_dir,
        )

    async def _preview_terminal_segment(
        self, segment, screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Preview a terminal segment using ttyd."""
        find_ttyd()  # Validate ttyd exists (raises if not)
        port = 7682

        self._ttyd_process = start_ttyd(port)
        await asyncio.sleep(0.5)

        try:
            return await self._run_terminal_session(port, segment, screenshot_dir)
        finally:
            stop_ttyd(self._ttyd_process)

    async def _run_terminal_session(
        self, port: int, segment, screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Run terminal session in browser."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await self._setup_terminal_page(browser, port)

            # Capture initial frame
            if self.capture_frames and self._frames_dir:
                await self._capture_frame(page, "terminal")

            results = await self._execute_terminal_commands(page, segment, screenshot_dir)
            await browser.close()
        return results

    async def _setup_terminal_page(self, browser, port: int):
        """Set up browser page for terminal viewing."""
        page = await self._create_terminal_context(browser, port)
        await self._configure_terminal(page)
        return page

    async def _create_terminal_context(self, browser, port: int):
        """Create browser context and navigate to terminal."""
        context = await browser.new_context(viewport={"width": self.width, "height": self.height})
        page = await context.new_page()
        await page.goto(f"http://localhost:{port}", wait_until="networkidle")
        await page.wait_for_selector(".xterm-screen", timeout=10000)
        await page.wait_for_function("() => window.term !== undefined", timeout=10000)
        await asyncio.sleep(0.3)
        return page

    async def _configure_terminal(self, page):
        """Configure terminal sizing and clear screen."""
        await setup_container(page)
        await fit_to_rows(page, self.rows, max_iterations=10, delay=0.1)
        await page.keyboard.press("Control+l")
        await asyncio.sleep(0.3)

    async def _execute_terminal_commands(
        self, page, segment, screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Execute terminal commands with frame capture."""
        results: list[CheckpointResult] = []
        # Terminal checkpoint detection is simplified - no visual selection tracking here

        for cmd in segment.commands:
            await self._dispatch_terminal_command(page, cmd)

            # Capture frame after command
            if self.capture_frames and self._frames_dir:
                await asyncio.sleep(0.05)
                await self._capture_frame(page, "terminal")

        return results

    async def _dispatch_terminal_command(self, page, cmd):
        """Dispatch a terminal command."""
        if cmd.name == "Type":
            await self._type_text(page, cmd.args[0] if cmd.args else "")
        elif cmd.name == "Enter":
            await page.keyboard.press("Enter")
        elif cmd.name == "Escape":
            await page.keyboard.press("Escape")
        elif cmd.name == "Sleep":
            duration = self._parse_duration(cmd.args[0]) if cmd.args else 0.5
            await asyncio.sleep(duration)
        elif cmd.name in ("Ctrl+l", "Clear"):
            await page.keyboard.press("Control+l")
        await asyncio.sleep(0.05)

    async def _type_text(self, page, text: str):
        """Type text character by character."""
        for char in text:
            await page.keyboard.type(char, delay=0)
            await asyncio.sleep(0.02)

    def _parse_duration(self, duration_str: str) -> float:
        """Parse duration string like '1s', '500ms', '0.5s'."""
        duration_str = duration_str.strip().lower()
        if duration_str.endswith("ms"):
            return float(duration_str[:-2]) / 1000
        elif duration_str.endswith("s"):
            return float(duration_str[:-1])
        else:
            return float(duration_str)

    async def _preview_browser_segment(
        self, segment, screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Preview a browser segment."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={"width": self.width, "height": self.height},
            )
            page = await context.new_page()

            # Capture initial frame
            if self.capture_frames and self._frames_dir:
                await self._capture_frame(page, "browser")

            results = await self._execute_browser_commands(page, segment, screenshot_dir)
            await browser.close()
        return results

    async def _execute_browser_commands(
        self, page, segment, screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Execute browser commands with frame capture."""
        from .modes.browser import BROWSER_COMMANDS

        results: list[CheckpointResult] = []

        for cmd in segment.commands:
            handler = BROWSER_COMMANDS.get(cmd.name)
            if handler:
                await handler(page, cmd)

            # Capture frame after command
            if self.capture_frames and self._frames_dir:
                await asyncio.sleep(0.1)  # More time for browser rendering
                await self._capture_frame(page, "browser")

        return results

    async def _capture_frame(self, page, mode: str) -> Path | None:
        """Capture a frame (terminal as .txt, browser as .png)."""
        if not self._frames_dir or self._start_time is None:
            return None

        self._frame_counter += 1
        elapsed = time.time() - self._start_time
        ext = "txt" if mode == "terminal" else "png"
        filepath = self._frames_dir / f"frame_{self._frame_counter:04d}_{elapsed:06.2f}.{ext}"

        if mode == "terminal":
            return await self._save_terminal_frame(page, filepath)
        await page.screenshot(path=str(filepath))
        return filepath

    async def _save_terminal_frame(self, page, filepath: Path) -> Path | None:
        """Save terminal buffer state to text file."""
        buffer_state = await get_buffer_state(page)
        if buffer_state and buffer_state.visible_lines:
            filepath.write_text("\n".join(buffer_state.visible_lines))
            return filepath
        return None
