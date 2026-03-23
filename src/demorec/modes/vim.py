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
import subprocess
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


def install_vim() -> bool:
    """Install vim if not present. Returns True if vim is available after.

    This runs BEFORE recording starts, so installation doesn't appear in video.
    """
    if check_vim_installed():
        return True

    # Try to install vim (Debian/Ubuntu)
    try:
        subprocess.run(["sudo", "apt-get", "update", "-qq"], capture_output=True, timeout=60)
        result = subprocess.run(
            ["sudo", "apt-get", "install", "-y", "-qq", "vim"], capture_output=True, timeout=120
        )
        return result.returncode == 0 and check_vim_installed()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def preflight_check() -> list[str]:
    """Run preflight checks for vim primitives.

    Returns list of error messages (empty if all checks pass).
    Called before recording begins to ensure dependencies are ready.
    """
    errors = []

    if not check_vim_installed():
        # Try to install
        if not install_vim():
            errors.append(
                "vim is not installed and automatic installation failed. "
                "Please install vim manually: sudo apt-get install vim"
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
    num_lines = end_line - start_line + 1
    available_rows = terminal_rows - 2

    if centering == "auto":
        if num_lines <= available_rows // 2:
            center_line = (start_line + end_line) // 2
            return [(f"{center_line}G", 0.2), ("zz", 0.3)]
        return [(f"{start_line}G", 0.2), ("zt", 0.3)]
    elif centering == "top":
        return [(f"{start_line}G", 0.2), ("zt", 0.3)]
    elif centering == "center":
        center_line = (start_line + end_line) // 2
        return [(f"{center_line}G", 0.2), ("zz", 0.3)]
    elif centering == "bottom":
        return [(f"{end_line}G", 0.2), ("zb", 0.3)]
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
    """Generate commands to go to a specific line.

    Args:
        line: Line number to go to
        state: VimState to update
        centering: How to position the line ("top", "center", "bottom")

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    commands = []

    # Exit visual mode if needed
    if state.in_visual_mode:
        commands.append(("ESCAPE", 0.2))
        state.in_visual_mode = False

    # Go to line
    commands.append((f"{line}G", 0.2))

    # Center appropriately
    if centering == "top":
        commands.append(("zt", 0.3))
    elif centering == "center":
        commands.append(("zz", 0.3))
    elif centering == "bottom":
        commands.append(("zb", 0.3))

    state.current_line = line

    return commands


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
        """Expand a high-level command into keystrokes.

        Args:
            cmd_name: Command name (Open, Highlight, Close, Goto)
            cmd_args: Command arguments

        Returns:
            List of (keys_to_type, delay_after) tuples
            Special keys: "ENTER", "ESCAPE", "TAB"
        """
        commands = []

        if cmd_name == "Open":
            if cmd_args:
                commands.extend(generate_open_commands(cmd_args[0], self.state))

        elif cmd_name == "Highlight":
            if cmd_args:
                line_range = cmd_args[0]
                centering = cmd_args[1] if len(cmd_args) > 1 else "auto"
                commands.extend(generate_highlight_commands(line_range, self.state, centering))

        elif cmd_name == "Close":
            commands.extend(generate_close_commands(self.state))

        elif cmd_name == "Goto":
            if cmd_args:
                line = int(cmd_args[0])
                centering = cmd_args[1] if len(cmd_args) > 1 else "center"
                commands.extend(generate_goto_commands(line, self.state, centering))

        return commands

    def is_vim_command(self, cmd_name: str) -> bool:
        """Check if a command is a high-level vim command."""
        return cmd_name in ("Open", "Highlight", "Close", "Goto")
