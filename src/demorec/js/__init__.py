"""JavaScript utilities for browser automation."""

from pathlib import Path

_JS_DIR = Path(__file__).parent


def load_js(filename: str) -> str:
    """Load a JavaScript file from the js directory."""
    js_path = _JS_DIR / filename
    return js_path.read_text()


def get_terminal_resize_js() -> str:
    """Get the terminal resize JavaScript code."""
    return load_js("terminal_resize.js")


# Pre-load JS for efficiency
TERMINAL_RESIZE_JS = get_terminal_resize_js()
