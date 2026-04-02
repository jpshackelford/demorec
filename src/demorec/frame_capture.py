"""Shared frame capture utilities for preview modules.

Provides common functionality for capturing frames during preview,
used by both TerminalPreviewer and ScriptPreviewer.
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from .xterm import get_buffer_state


@dataclass
class FrameCaptureState:
    """Holds state for frame capture during preview."""

    capture_frames: bool = False
    screenshots: str = "on_error"
    frame_counter: int = 0
    start_time: float | None = None
    frames_dir: Path | None = None


def setup_frames_dir(state: FrameCaptureState, output_dir: Path | None):
    """Set up frames directory if frame capture is enabled."""
    if not state.capture_frames or not output_dir:
        state.frames_dir = None
        return
    state.frames_dir = output_dir
    try:
        state.frames_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Cannot create frames directory {output_dir}: {e}") from e
    state.frame_counter = 0
    state.start_time = None


def setup_screenshot_dir(state: FrameCaptureState, output_dir: Path | None) -> Path | None:
    """Set up screenshot directory if needed."""
    if state.screenshots == "never":
        return None
    screenshot_dir = output_dir or Path(".demorec_preview")
    screenshot_dir.mkdir(exist_ok=True)
    return screenshot_dir


def init_start_time(state: FrameCaptureState):
    """Initialize start time for frame capture."""
    if state.capture_frames and state.frames_dir:
        state.start_time = time.time()


async def capture_frame(state: FrameCaptureState, page, mode: str) -> Path | None:
    """Capture a frame (terminal as .txt, browser as .png)."""
    if not state.frames_dir or state.start_time is None:
        return None

    state.frame_counter += 1
    elapsed = time.time() - state.start_time
    ext = "txt" if mode == "terminal" else "png"
    filepath = state.frames_dir / f"frame_{state.frame_counter:04d}_{elapsed:07.2f}.{ext}"

    if mode == "terminal":
        return await _save_terminal_frame(page, filepath)
    await page.screenshot(path=str(filepath))
    return filepath


async def _save_terminal_frame(page, filepath: Path) -> Path | None:
    """Save terminal buffer state to text file."""
    buffer_state = await get_buffer_state(page)
    if buffer_state and buffer_state.visible_lines:
        filepath.write_text("\n".join(buffer_state.visible_lines))
        return filepath
    return None


def parse_duration(duration_str: str) -> float:
    """Parse duration string like '1s', '500ms', '0.5s'."""
    duration_str = duration_str.strip().lower()
    if duration_str.endswith("ms"):
        return float(duration_str[:-2]) / 1000
    elif duration_str.endswith("s"):
        return float(duration_str[:-1])
    return float(duration_str)


async def type_text(page, text: str):
    """Type text character by character."""
    for char in text:
        await page.keyboard.type(char, delay=0)
        await asyncio.sleep(0.02)


async def dispatch_terminal_command(page, cmd):
    """Dispatch a terminal command to the page."""
    if cmd.name == "Type":
        await type_text(page, cmd.args[0] if cmd.args else "")
    elif cmd.name == "Enter":
        await page.keyboard.press("Enter")
    elif cmd.name == "Escape":
        await page.keyboard.press("Escape")
    elif cmd.name == "Sleep":
        await asyncio.sleep(parse_duration(cmd.args[0]) if cmd.args else 0.5)
    elif cmd.name in ("Ctrl+l", "Clear"):
        await page.keyboard.press("Control+l")
