"""High-level vim primitives for code review demos.

Provides Open, Highlight, and Close commands that handle all the vim
complexity internally, including:
- Opening files with line numbers enabled
- Calculating proper scroll positions based on terminal rows
- Visual line selection for highlights
- Clean exit

Preflight checks ensure vim is installed before recording begins.

Example usage in .demorec:
    @mode terminal
    @terminal:rows 30

    Open "src/api.py"
    Highlight 6-8
    Highlight 27-35
    Close
"""

import shutil
from dataclasses import dataclass


@dataclass
class VimState:
    """Tracks vim session state."""

    file_path: str | None = None
    current_line: int = 1
    terminal_rows: int = 24
    in_visual_mode: bool = False
    file_total_lines: int | None = None


def check_vim_installed() -> bool:
    """Check if vim is available on the system."""
    return shutil.which("vim") is not None


def preflight_check() -> list[str]:
    """Run preflight checks for vim primitives.

    Returns list of error messages (empty if all checks pass).
    Called before recording begins to ensure dependencies are ready.
    """
    errors = []

    if not check_vim_installed():
        errors.append(
            "vim is not installed. Please install vim manually:\n"
            "  Ubuntu/Debian: sudo apt-get install vim\n"
            "  macOS: brew install vim\n"
            "  Fedora/RHEL: sudo dnf install vim"
        )

    return errors


def generate_open_commands(file_path: str, state: VimState) -> list[tuple[str, float]]:
    """Generate commands to open a file in vim with line numbers.

    Args:
        file_path: Path to the file to open
        state: VimState to update

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    state.file_path = file_path
    state.current_line = 1
    state.in_visual_mode = False

    commands = []

    # Open file in vim with:
    # -i NONE: Ignore viminfo (don't remember last cursor position)
    # +1: Start at line 1
    commands.append((f"vim -i NONE +1 {file_path}", 0))
    commands.append(("ENTER", 1.0))  # Wait for vim to load

    # Enable line numbers
    commands.append((":set number", 0))
    commands.append(("ENTER", 0.3))

    return commands


def generate_highlight_commands(
    line_range: str, state: VimState, centering: str = "auto"
) -> list[tuple[str, float]]:
    """Generate vim commands to highlight a range of lines."""
    start_line, end_line = _parse_line_range(line_range)
    commands = []

    if state.in_visual_mode:
        commands.append(("ESCAPE", 0.2))
        state.in_visual_mode = False

    commands.extend(_centering_commands(start_line, end_line, state.terminal_rows, centering))
    commands.extend(_visual_select_commands(start_line, end_line))

    state.in_visual_mode = True
    state.current_line = end_line
    return commands


def _parse_line_range(line_range: str) -> tuple[int, int]:
    """Parse line range like '6-8' or '27' into (start, end)."""
    if "-" in line_range:
        start, end = map(int, line_range.split("-"))
        return start, end
    line = int(line_range)
    return line, line


def _centering_commands(
    start_line: int, end_line: int, terminal_rows: int, centering: str
) -> list[tuple[str, float]]:
    """Generate commands to position the selection in viewport."""
    if centering == "auto":
        return _auto_centering(start_line, end_line, terminal_rows)
    return _fixed_centering(start_line, end_line, centering)


def _auto_centering(start: int, end: int, rows: int) -> list[tuple[str, float]]:
    """Auto-select centering based on selection size."""
    num_lines, available = end - start + 1, rows - 2
    if num_lines <= available // 2:
        return [(f"{(start + end) // 2}G", 0.2), ("zz", 0.3)]
    return [(f"{start}G", 0.2), ("zt", 0.3)]


def _fixed_centering(start: int, end: int, mode: str) -> list[tuple[str, float]]:
    """Apply fixed centering mode."""
    if mode == "top":
        return [(f"{start}G", 0.2), ("zt", 0.3)]
    if mode == "center":
        return [(f"{(start + end) // 2}G", 0.2), ("zz", 0.3)]
    if mode == "bottom":
        return [(f"{end}G", 0.2), ("zb", 0.3)]
    return []


def _visual_select_commands(start_line: int, end_line: int) -> list[tuple[str, float]]:
    """Generate visual selection commands."""
    commands = [(f"{start_line}G", 0.2), ("V", 0.2)]
    if end_line > start_line:
        commands.append((f"{end_line}G", 0.3))
    return commands


def generate_close_commands(state: VimState) -> list[tuple[str, float]]:
    """Generate commands to cleanly exit vim.

    Args:
        state: VimState to check current mode

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    commands = []

    # Exit visual mode if needed
    if state.in_visual_mode:
        commands.append(("ESCAPE", 0.2))
        state.in_visual_mode = False

    # Quit without saving
    commands.append(("ESCAPE", 0.2))  # Ensure we're in normal mode
    commands.append((":q!", 0))
    commands.append(("ENTER", 0.5))

    # Clear state
    state.file_path = None
    state.current_line = 1

    return commands


def generate_goto_commands(
    line: int, state: VimState, centering: str = "center"
) -> list[tuple[str, float]]:
    """Generate commands to go to a specific line."""
    commands = _exit_visual_if_needed(state)
    commands.append((f"{line}G", 0.2))
    commands.extend(_get_centering_cmd(centering))
    state.current_line = line
    return commands


def _exit_visual_if_needed(state: VimState) -> list[tuple[str, float]]:
    """Exit visual mode if active."""
    if state.in_visual_mode:
        state.in_visual_mode = False
        return [("ESCAPE", 0.2)]
    return []


def _get_centering_cmd(centering: str) -> list[tuple[str, float]]:
    """Get centering command for the specified mode."""
    cmds = {"top": [("zt", 0.3)], "center": [("zz", 0.3)], "bottom": [("zb", 0.3)]}
    return cmds.get(centering, [])


class VimCommandExpander:
    """Expands high-level vim commands into low-level terminal commands.

    This class is used by the terminal recorder to expand Open, Highlight,
    and Close commands into the actual keystrokes needed.

    Note: Vim installation is handled by preflight_check() before recording.
    """

    def __init__(self, terminal_rows: int = 24):
        self.state = VimState(terminal_rows=terminal_rows)

    def set_terminal_rows(self, rows: int):
        """Update terminal row count for scroll calculations."""
        self.state.terminal_rows = rows

    def expand_command(self, cmd_name: str, cmd_args: list[str]) -> list[tuple[str, float]]:
        """Expand a high-level command into keystrokes."""
        handlers = {
            "Open": self._expand_open,
            "Highlight": self._expand_highlight,
            "Close": self._expand_close,
            "Goto": self._expand_goto,
        }
        handler = handlers.get(cmd_name)
        return handler(cmd_args) if handler else []

    def _expand_open(self, args: list[str]) -> list[tuple[str, float]]:
        return generate_open_commands(args[0], self.state) if args else []

    def _expand_highlight(self, args: list[str]) -> list[tuple[str, float]]:
        if not args:
            return []
        centering = args[1] if len(args) > 1 else "auto"
        return generate_highlight_commands(args[0], self.state, centering)

    def _expand_close(self, args: list[str]) -> list[tuple[str, float]]:
        return generate_close_commands(self.state)

    def _expand_goto(self, args: list[str]) -> list[tuple[str, float]]:
        if not args:
            return []
        centering = args[1] if len(args) > 1 else "center"
        return generate_goto_commands(int(args[0]), self.state, centering)

    def is_vim_command(self, cmd_name: str) -> bool:
        """Check if a command is a high-level vim command."""
        return cmd_name in ("Open", "Highlight", "Close", "Goto")
