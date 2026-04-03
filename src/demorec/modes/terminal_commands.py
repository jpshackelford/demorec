"""Terminal command handlers and themes.

Contains the dispatch table for terminal commands and color themes.
"""

import asyncio

from ..parser import parse_time

# Color themes
THEMES = {
    "dracula": {
        "background": "#282a36",
        "foreground": "#f8f8f2",
        "cursor": "#f8f8f2",
        "cursorAccent": "#282a36",
        "selectionBackground": "#44475a",
        "black": "#21222c",
        "red": "#ff5555",
        "green": "#50fa7b",
        "yellow": "#f1fa8c",
        "blue": "#bd93f9",
        "magenta": "#ff79c6",
        "cyan": "#8be9fd",
        "white": "#f8f8f2",
        "brightBlack": "#6272a4",
        "brightRed": "#ff6e6e",
        "brightGreen": "#69ff94",
        "brightYellow": "#ffffa5",
        "brightBlue": "#d6acff",
        "brightMagenta": "#ff92df",
        "brightCyan": "#a4ffff",
        "brightWhite": "#ffffff",
    },
    "github-dark": {
        "background": "#0d1117",
        "foreground": "#c9d1d9",
        "cursor": "#c9d1d9",
        "cursorAccent": "#0d1117",
        "selectionBackground": "#3b5070",
        "black": "#484f58",
        "red": "#ff7b72",
        "green": "#3fb950",
        "yellow": "#d29922",
        "blue": "#58a6ff",
        "magenta": "#bc8cff",
        "cyan": "#39c5cf",
        "white": "#b1bac4",
        "brightBlack": "#6e7681",
        "brightRed": "#ffa198",
        "brightGreen": "#56d364",
        "brightYellow": "#e3b341",
        "brightBlue": "#79c0ff",
        "brightMagenta": "#d2a8ff",
        "brightCyan": "#56d4dd",
        "brightWhite": "#f0f6fc",
    },
}


# Command handlers
async def _cmd_set_theme(recorder, page, cmd):
    """SetTheme is processed before recording starts."""
    pass


async def _cmd_type(recorder, page, cmd):
    """Type text into the terminal."""
    if cmd.args:
        await recorder._send_keys(page, cmd.args[0])


async def _cmd_enter(recorder, page, cmd):
    """Press Enter key."""
    await page.keyboard.press("Enter")
    await asyncio.sleep(0.3)


async def _cmd_run(recorder, page, cmd):
    """Type and execute a command."""
    if cmd.args:
        await recorder._send_keys(page, cmd.args[0])
        await page.keyboard.press("Enter")
        wait_time = parse_time(cmd.args[1]) if len(cmd.args) > 1 else 1.0
        await asyncio.sleep(wait_time)


async def _cmd_sleep(recorder, page, cmd):
    """Sleep for a duration."""
    if cmd.args:
        await asyncio.sleep(parse_time(cmd.args[0]))


async def _cmd_ctrl_key(recorder, page, cmd, key: str, delay: float = 0.1):
    """Press a Ctrl+key combination."""
    await page.keyboard.press(f"Control+{key}")
    await asyncio.sleep(delay)


async def _cmd_ctrl_c(recorder, page, cmd):
    await _cmd_ctrl_key(recorder, page, cmd, "c")


async def _cmd_ctrl_d(recorder, page, cmd):
    await _cmd_ctrl_key(recorder, page, cmd, "d")


async def _cmd_ctrl_l(recorder, page, cmd):
    await _cmd_ctrl_key(recorder, page, cmd, "l")


async def _cmd_ctrl_z(recorder, page, cmd):
    await _cmd_ctrl_key(recorder, page, cmd, "z")


async def _cmd_ctrl_j(recorder, page, cmd):
    """Ctrl+J - Submit multi-line input in OpenHands CLI."""
    await _cmd_ctrl_key(recorder, page, cmd, "j")


async def _cmd_ctrl_p(recorder, page, cmd):
    """Ctrl+P - Open command palette in OpenHands CLI."""
    await _cmd_ctrl_key(recorder, page, cmd, "p")


async def _cmd_ctrl_q(recorder, page, cmd):
    """Ctrl+Q - Quit OpenHands CLI."""
    await _cmd_ctrl_key(recorder, page, cmd, "q")


async def _cmd_ctrl_o(recorder, page, cmd):
    """Ctrl+O - Toggle cells view in OpenHands CLI."""
    await _cmd_ctrl_key(recorder, page, cmd, "o")


async def _cmd_ctrl_x(recorder, page, cmd):
    """Ctrl+X - Open external editor in OpenHands CLI."""
    await _cmd_ctrl_key(recorder, page, cmd, "x")


async def _cmd_tab(recorder, page, cmd):
    """Press Tab key."""
    await page.keyboard.press("Tab")
    await asyncio.sleep(0.2)


async def _cmd_arrow(recorder, page, cmd, direction: str):
    """Press an arrow key."""
    await page.keyboard.press(f"Arrow{direction}")
    await asyncio.sleep(0.1)


async def _cmd_up(recorder, page, cmd):
    await _cmd_arrow(recorder, page, cmd, "Up")


async def _cmd_down(recorder, page, cmd):
    await _cmd_arrow(recorder, page, cmd, "Down")


async def _cmd_backspace(recorder, page, cmd):
    """Press Backspace key one or more times."""
    count = int(cmd.args[0]) if cmd.args else 1
    for _ in range(count):
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.05)


async def _cmd_escape(recorder, page, cmd):
    """Press Escape key."""
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.1)


async def _cmd_space(recorder, page, cmd):
    """Press Space key."""
    await page.keyboard.press("Space")
    await asyncio.sleep(0.05)


async def _cmd_clear(recorder, page, cmd):
    """Clear the terminal screen."""
    await page.keyboard.press("Control+l")
    await asyncio.sleep(0.1)


# Command dispatch table
TERMINAL_COMMANDS = {
    "SetTheme": _cmd_set_theme,
    "Type": _cmd_type,
    "Enter": _cmd_enter,
    "Run": _cmd_run,
    "Sleep": _cmd_sleep,
    "Ctrl+C": _cmd_ctrl_c,
    "Ctrl+D": _cmd_ctrl_d,
    "Ctrl+J": _cmd_ctrl_j,
    "Ctrl+L": _cmd_ctrl_l,
    "Ctrl+O": _cmd_ctrl_o,
    "Ctrl+P": _cmd_ctrl_p,
    "Ctrl+Q": _cmd_ctrl_q,
    "Ctrl+X": _cmd_ctrl_x,
    "Ctrl+Z": _cmd_ctrl_z,
    "Tab": _cmd_tab,
    "Up": _cmd_up,
    "Down": _cmd_down,
    "Backspace": _cmd_backspace,
    "Escape": _cmd_escape,
    "Space": _cmd_space,
    "Clear": _cmd_clear,
}
