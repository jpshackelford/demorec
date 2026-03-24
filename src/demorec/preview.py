"""Preview runner for verifying terminal recordings at checkpoints.

Runs through a script, pausing at auto-detected checkpoints to verify
that expected content is visible on screen.
"""

import asyncio
import re
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


class TerminalPreviewer:
    """Previews a terminal recording, verifying checkpoints."""

    def __init__(
        self,
        rows: int = 30,
        width: int = 1280,
        height: int = 720,
        screenshots: str = "on_error",
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
        self, script_path: Path, segment, output_dir: Path | None
    ) -> PreviewResult:
        checkpoints = self._detect_checkpoints_from_commands(segment.commands)
        screenshot_dir = self._setup_screenshot_dir(output_dir)

        find_ttyd()  # Validate ttyd exists (raises if not)
        port = 7682

        self._ttyd_process = start_ttyd(port)
        await asyncio.sleep(0.5)

        try:
            results = await self._run_browser_session(port, segment, checkpoints, screenshot_dir)
        finally:
            stop_ttyd(self._ttyd_process)

        return self._build_result(results, screenshot_dir)

    def _setup_screenshot_dir(self, output_dir: Path | None) -> Path | None:
        """Set up screenshot directory if needed."""
        if self.screenshots == "never":
            return None
        screenshot_dir = output_dir or Path(".demorec_preview")
        screenshot_dir.mkdir(exist_ok=True)
        return screenshot_dir

    def _build_result(
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

        for cmd_idx, cmd in enumerate(segment.commands):
            await self._execute_command(page, cmd)
            if cmd_idx in checkpoint_map:
                await asyncio.sleep(0.5)
                result = await self._verify_checkpoint(
                    page, checkpoint_map[cmd_idx], screenshot_dir, len(results) + 1
                )
                results.append(result)
        return results

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
