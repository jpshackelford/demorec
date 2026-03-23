"""JavaScript utilities for browser automation."""

import functools
from pathlib import Path

_JS_DIR = Path(__file__).parent


def load_js(filename: str) -> str:
    """Load a JavaScript file from the js directory."""
    js_path = _JS_DIR / filename
    return js_path.read_text()


@functools.lru_cache(maxsize=1)
def get_terminal_resize_js() -> str:
    """Get the terminal resize JavaScript code.
    
    Uses lru_cache for efficiency - file is read only once.
    Lazy loading prevents import-time crashes if file is missing.
    """
    return load_js("terminal_resize.js")


def __getattr__(name: str):
    """Module-level __getattr__ for lazy loading of JS constants.
    
    Allows `from demorec.js import TERMINAL_RESIZE_JS` to work
    while deferring file I/O until first access.
    """
    if name == "TERMINAL_RESIZE_JS":
        return get_terminal_resize_js()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
