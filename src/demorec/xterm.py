"""xterm.js terminal configuration and setup.

Provides async functions to configure xterm.js terminals in the browser,
loading JS from static files for maintainability.
"""

import asyncio
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


def _load_js(name: str) -> str:
    """Load a JS file from the js/ package directory."""
    return files("demorec.js").joinpath(name).read_text()


# Load JS templates at module import time
SETUP_TERMINAL_JS = _load_js("setup_terminal.js")
FIT_TO_ROWS_JS = _load_js("fit_to_rows.js")
GET_BUFFER_STATE_JS = _load_js("get_buffer_state.js")
SETUP_CONTAINER_JS = _load_js("setup_container.js")


@dataclass
class TerminalConfig:
    """Configuration for terminal setup."""

    font_size: int = 14
    font_family: str = "Monaco, 'Cascadia Code', 'Fira Code', monospace"
    line_height: float = 1.0
    theme: dict | None = None
    desired_rows: int | None = None


@dataclass
class TerminalSize:
    """Terminal size information."""

    rows: int
    cols: int
    font_size: int
    baseline_rows: int | None = None
    done: bool = False


async def setup_terminal(page: Any, config: TerminalConfig) -> TerminalSize | None:
    """Set up terminal with full viewport and optional row targeting."""
    result = await page.evaluate(SETUP_TERMINAL_JS, _config_to_dict(config))
    return _parse_terminal_result(result) if result else None


def _config_to_dict(config: TerminalConfig) -> dict:
    """Convert TerminalConfig to JS parameter dict."""
    return {
        "fontSize": config.font_size,
        "fontFamily": config.font_family,
        "lineHeight": config.line_height,
        "theme": config.theme,
        "desiredRows": config.desired_rows,
    }


def _parse_terminal_result(result: dict) -> TerminalSize:
    """Parse JS result into TerminalSize."""
    return TerminalSize(
        rows=result["rows"],
        cols=result["cols"],
        font_size=result["fontSize"],
        baseline_rows=result.get("baselineRows"),
    )


async def fit_to_rows(
    page: Any, desired_rows: int, max_iterations: int = 5, delay: float = 0.2
) -> TerminalSize | None:
    """Iteratively adjust font size to achieve target row count."""
    size = None
    for _ in range(max_iterations):
        size = await _fit_iteration(page, desired_rows)
        if not size or size.done:
            return size
        await asyncio.sleep(delay)
    return size


async def _fit_iteration(page: Any, desired_rows: int) -> TerminalSize | None:
    """Run one font size adjustment iteration."""
    result = await page.evaluate(FIT_TO_ROWS_JS, desired_rows)
    if not result:
        return None
    return TerminalSize(
        rows=result["rows"],
        cols=result["cols"],
        font_size=result["fontSize"],
        done=result.get("done", False),
    )


@dataclass
class BufferState:
    """Terminal buffer state for checkpoint verification."""

    rows: int
    cols: int
    viewport_y: int
    visible_lines: list[str]


async def get_buffer_state(page: Any) -> BufferState | None:
    """Get current terminal buffer state.

    Args:
        page: Playwright page object

    Returns:
        BufferState with visible content, or None if term not found
    """
    result = await page.evaluate(GET_BUFFER_STATE_JS)

    if not result:
        return None

    return BufferState(
        rows=result["rows"],
        cols=result["cols"],
        viewport_y=result["viewportY"],
        visible_lines=result["visibleLines"],
    )


async def setup_container(
    page: Any,
    font_size: int = 14,
    font_family: str = "Monaco, 'Courier New', monospace",
) -> dict | None:
    """Simple container setup without row targeting.

    Args:
        page: Playwright page object
        font_size: Font size in pixels
        font_family: Font family string

    Returns:
        Dict with rows/cols, or None if term not found
    """
    return await page.evaluate(
        SETUP_CONTAINER_JS,
        {"fontSize": font_size, "fontFamily": font_family},
    )
