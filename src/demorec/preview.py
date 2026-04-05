"""Preview runner for verifying terminal recordings at checkpoints.

Runs through a script, pausing at auto-detected checkpoints to verify
that expected content is visible on screen. Also supports frame-by-frame
capture for AI debugging and verification.
"""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from .frame_capture import (
    FrameCaptureState,
    capture_frame,
    dispatch_terminal_command,
    init_start_time,
    parse_duration,
    setup_frames_dir,
    setup_screenshot_dir,
    type_text,
)
from .modes.openhands import OpenHandsCommandExpander, WaitForReadyConfig
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


def build_preview_result(
    results: list[CheckpointResult], screenshot_dir: Path | None, state: FrameCaptureState
) -> PreviewResult:
    """Build final PreviewResult from checkpoint results."""
    passed = sum(1 for r in results if r.passed)
    return PreviewResult(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
        screenshot_dir=screenshot_dir if results else None,
        frame_count=state.frame_counter,
        frames_dir=state.frames_dir,
    )


class TerminalPreviewer:
    """Previews a terminal recording, verifying checkpoints.

    Supports OpenHands CLI primitives (Install, Start, Prompt, etc.).
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
        self._ttyd_process = None
        self._state = FrameCaptureState(capture_frames=capture_frames, screenshots=screenshots)
        self._openhands_expander = OpenHandsCommandExpander()

    @property
    def screenshots(self) -> str:
        """Screenshots mode (for backward compatibility)."""
        return self._state.screenshots

    @property
    def capture_frames(self) -> bool:
        """Whether frame capture is enabled (for backward compatibility)."""
        return self._state.capture_frames

    def preview(self, script_path: Path, segment, output_dir: Path | None = None) -> PreviewResult:
        """Run preview and return results."""
        return asyncio.run(self._preview_async(script_path, segment, output_dir))

    async def _preview_async(
        self, script_path: Path, segment, output_dir: Path | None
    ) -> PreviewResult:
        checkpoints = self._detect_checkpoints_from_commands(segment.commands)
        screenshot_dir = setup_screenshot_dir(self._state, output_dir)
        setup_frames_dir(self._state, output_dir)

        find_ttyd()  # Validate ttyd exists (raises if not)
        port = 7682

        self._ttyd_process = start_ttyd(port)
        await asyncio.sleep(0.5)

        try:
            results = await self._run_browser_session(port, segment, checkpoints, screenshot_dir)
        finally:
            stop_ttyd(self._ttyd_process)

        return build_preview_result(results, screenshot_dir, self._state)

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
        """Execute commands and verify checkpoints.

        Captures frame BEFORE each command for debugging visibility.
        """
        results: list[CheckpointResult] = []
        checkpoint_map = {cp.command_index: cp for cp in checkpoints}
        await self._init_frame_capture(page)

        for cmd_idx, cmd in enumerate(segment.commands):
            # Capture frame BEFORE command for debugging
            await self._maybe_capture_frame(page)
            await self._execute_command(page, cmd)
            result = await self._maybe_verify_checkpoint(
                page, cmd_idx, checkpoint_map, screenshot_dir, len(results)
            )
            if result:
                results.append(result)
        return results

    async def _init_frame_capture(self, page):
        """Initialize timing for frame capture."""
        if self._state.capture_frames and self._state.frames_dir:
            init_start_time(self._state)

    async def _maybe_capture_frame(self, page):
        """Capture frame before command if enabled."""
        if self._state.capture_frames and self._state.frames_dir:
            await asyncio.sleep(0.05)
            await capture_frame(self._state, page, "terminal")

    async def _maybe_verify_checkpoint(
        self, page, cmd_idx: int, checkpoint_map: dict, screenshot_dir: Path | None, count: int
    ) -> CheckpointResult | None:
        """Verify checkpoint if current command index matches."""
        if cmd_idx not in checkpoint_map:
            return None
        await asyncio.sleep(0.5)
        cp = checkpoint_map[cmd_idx]
        return await self._verify_checkpoint(page, cp, screenshot_dir, count + 1)

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
        """Dispatch command to appropriate handler.

        Handles OpenHands CLI primitives specially, expanding them to keystrokes.
        """
        if self._openhands_expander.is_openhands_command(cmd.name):
            await self._execute_openhands_command(page, cmd)
        else:
            await dispatch_terminal_command(page, cmd)

    async def _execute_openhands_command(self, page, cmd):
        """Execute an OpenHands CLI primitive command."""
        try:
            expanded = self._openhands_expander.expand_command(cmd.name, cmd.args)
        except ValueError as e:
            print(f"Warning: {e}")
            return

        if isinstance(expanded, WaitForReadyConfig):
            await self._wait_for_ready(page, expanded)
            return

        for keystroke, delay in expanded:
            await self._execute_keystroke(page, keystroke)
            if delay > 0:
                await asyncio.sleep(delay)

    async def _execute_keystroke(self, page, keystroke: str):
        """Execute a single keystroke or key sequence."""
        key_map = {
            "ENTER": "Enter",
            "CTRL+L": "Control+l",
            "CTRL+J": "Control+j",
            "CTRL+P": "Control+p",
            "CTRL+Q": "Control+q",
            "CTRL+C": "Control+c",
        }
        upper = keystroke.upper()
        if upper in key_map:
            await page.keyboard.press(key_map[upper])
        else:
            await type_text(page, keystroke)

    async def _wait_for_ready(self, page, config: WaitForReadyConfig):
        """Wait for terminal to show ready pattern.

        If pattern starts with '!', waits for the pattern to NOT be present
        (negative matching). For negative patterns, first waits briefly for
        the pattern to appear (giving the process time to start), then waits
        for it to disappear.
        """
        import time

        # Check for negative pattern (absence detection)
        is_negative = config.pattern.startswith("!")
        pattern_str = config.pattern[1:] if is_negative else config.pattern
        pattern = re.compile(pattern_str)
        start = time.time()

        # For negative patterns, first wait for the pattern to appear
        # (give process up to 5 seconds to start showing the indicator)
        if is_negative:
            appeared = False
            while time.time() - start < 5.0:
                buffer_state = await get_buffer_state(page)
                if buffer_state and buffer_state.visible_lines:
                    if any(pattern.search(line) for line in buffer_state.visible_lines):
                        appeared = True
                        break
                await asyncio.sleep(config.poll_interval)
            # Reset start time for the main wait
            start = time.time()

        while time.time() - start < config.timeout:
            buffer_state = await get_buffer_state(page)
            if buffer_state and buffer_state.visible_lines:
                # Check all visible lines for the pattern
                found = any(
                    pattern.search(line) for line in buffer_state.visible_lines
                )
                if is_negative:
                    # Negative: ready when pattern is NOT found
                    if not found:
                        return
                else:
                    # Positive: ready when pattern IS found
                    if found:
                        return
            await asyncio.sleep(config.poll_interval)

        print(
            f"WaitForReady: Timeout after {time.time() - start:.1f}s "
            f"waiting for pattern '{config.pattern}'"
        )

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
        should_screenshot = self._state.screenshots == "always" or (
            self._state.screenshots == "on_error" and not passed
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
    Supports OpenHands CLI primitives (Install, Start, Prompt, etc.).
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
        self._ttyd_process = None
        self._state = FrameCaptureState(capture_frames=capture_frames, screenshots=screenshots)
        self._openhands_expander = OpenHandsCommandExpander()

    @property
    def screenshots(self) -> str:
        """Screenshots mode (for backward compatibility)."""
        return self._state.screenshots

    @property
    def capture_frames(self) -> bool:
        """Whether frame capture is enabled (for backward compatibility)."""
        return self._state.capture_frames

    def preview(
        self, script_path: Path, segments: list, output_dir: Path | None = None
    ) -> PreviewResult:
        """Run preview across all segments and return results."""
        return asyncio.run(self._preview_async(script_path, segments, output_dir))

    async def _preview_async(
        self, script_path: Path, segments: list, output_dir: Path | None
    ) -> PreviewResult:
        """Async preview for terminal and browser segments."""
        setup_frames_dir(self._state, output_dir)
        screenshot_dir = setup_screenshot_dir(self._state, output_dir)
        init_start_time(self._state)
        results = [await self._preview_segment(s, screenshot_dir) for s in segments]
        return build_preview_result(sum(results, []), screenshot_dir, self._state)

    async def _preview_segment(self, segment, screenshot_dir) -> list[CheckpointResult]:
        """Preview a segment (terminal or browser)."""
        if segment.mode == "terminal":
            return await self._preview_terminal_segment(segment, screenshot_dir)
        if segment.mode == "browser":
            return await self._preview_browser_segment(segment, screenshot_dir)
        return []

    async def _preview_terminal_segment(
        self, segment, screenshot_dir: Path | None
    ) -> list[CheckpointResult]:
        """Preview a terminal segment using ttyd."""
        find_ttyd()
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

            if self._state.capture_frames and self._state.frames_dir:
                await capture_frame(self._state, page, "terminal")

            results = await self._execute_terminal_commands(page, segment)
            await browser.close()
        return results

    async def _setup_terminal_page(self, browser, port: int):
        """Set up browser page for terminal viewing."""
        context = await browser.new_context(viewport={"width": self.width, "height": self.height})
        page = await context.new_page()
        await page.goto(f"http://localhost:{port}", wait_until="networkidle")
        await page.wait_for_selector(".xterm-screen", timeout=10000)
        await page.wait_for_function("() => window.term !== undefined", timeout=10000)
        await asyncio.sleep(0.3)
        await setup_container(page)
        await fit_to_rows(page, self.rows, max_iterations=10, delay=0.1)
        await page.keyboard.press("Control+l")
        await asyncio.sleep(0.3)
        return page

    async def _execute_terminal_commands(self, page, segment) -> list[CheckpointResult]:
        """Execute terminal commands with frame capture.

        Handles both standard terminal commands and OpenHands CLI primitives.
        Captures frame BEFORE each command for debugging visibility.
        """
        for cmd in segment.commands:
            # Capture frame BEFORE command for debugging
            if self._state.capture_frames and self._state.frames_dir:
                await capture_frame(self._state, page, "terminal")

            # Check if this is an OpenHands CLI primitive
            if self._openhands_expander.is_openhands_command(cmd.name):
                await self._execute_openhands_command(page, cmd)
            else:
                await dispatch_terminal_command(page, cmd)
            await asyncio.sleep(0.05)
        return []

    async def _execute_openhands_command(self, page, cmd):
        """Execute an OpenHands CLI primitive command.

        Expands the high-level command (Install, Start, Prompt, etc.)
        into low-level keystrokes and executes them.
        """
        try:
            expanded = self._openhands_expander.expand_command(cmd.name, cmd.args)
        except ValueError as e:
            # State validation error (e.g., Prompt before Start)
            print(f"Warning: {e}")
            return

        # Handle WaitForReady specially - poll for pattern match
        if isinstance(expanded, WaitForReadyConfig):
            await self._wait_for_ready(page, expanded)
            return

        # Execute expanded keystrokes
        for keystroke, delay in expanded:
            await self._execute_keystroke(page, keystroke)
            if delay > 0:
                await asyncio.sleep(delay)

    async def _execute_keystroke(self, page, keystroke: str):
        """Execute a single keystroke or key sequence."""
        key_map = {
            "ENTER": "Enter",
            "CTRL+L": "Control+l",
            "CTRL+J": "Control+j",
            "CTRL+P": "Control+p",
            "CTRL+Q": "Control+q",
            "CTRL+C": "Control+c",
        }
        upper = keystroke.upper()
        if upper in key_map:
            await page.keyboard.press(key_map[upper])
        else:
            # Type regular text
            await type_text(page, keystroke)

    async def _wait_for_ready(self, page, config: WaitForReadyConfig):
        """Wait for terminal to show ready pattern.

        If pattern starts with '!', waits for the pattern to NOT be present
        (negative matching). For negative patterns, first waits briefly for
        the pattern to appear (giving the process time to start), then waits
        for it to disappear.
        """
        import time

        # Check for negative pattern (absence detection)
        is_negative = config.pattern.startswith("!")
        pattern_str = config.pattern[1:] if is_negative else config.pattern
        pattern = re.compile(pattern_str)
        start = time.time()

        # For negative patterns, first wait for the pattern to appear
        # (give process up to 5 seconds to start showing the indicator)
        if is_negative:
            appeared = False
            while time.time() - start < 5.0:
                buffer_state = await get_buffer_state(page)
                if buffer_state and buffer_state.visible_lines:
                    if any(pattern.search(line) for line in buffer_state.visible_lines):
                        appeared = True
                        break
                await asyncio.sleep(config.poll_interval)
            # Reset start time for the main wait
            start = time.time()

        while time.time() - start < config.timeout:
            buffer_state = await get_buffer_state(page)
            if buffer_state and buffer_state.visible_lines:
                # Check all visible lines for the pattern
                found = any(
                    pattern.search(line) for line in buffer_state.visible_lines
                )
                if is_negative:
                    # Negative: ready when pattern is NOT found
                    if not found:
                        return
                else:
                    # Positive: ready when pattern IS found
                    if found:
                        return
            await asyncio.sleep(config.poll_interval)

        print(
            f"WaitForReady: Timeout after {time.time() - start:.1f}s "
            f"waiting for pattern '{config.pattern}'"
        )

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

            if self._state.capture_frames and self._state.frames_dir:
                await capture_frame(self._state, page, "browser")

            results = await self._execute_browser_commands(page, segment)
            await browser.close()
        return results

    async def _execute_browser_commands(self, page, segment) -> list[CheckpointResult]:
        """Execute browser commands with frame capture."""
        from .modes.browser import BROWSER_COMMANDS

        for cmd in segment.commands:
            handler = BROWSER_COMMANDS.get(cmd.name)
            if handler:
                await handler(page, cmd)
            if self._state.capture_frames and self._state.frames_dir:
                await asyncio.sleep(0.1)
                await capture_frame(self._state, page, "browser")
        return []
