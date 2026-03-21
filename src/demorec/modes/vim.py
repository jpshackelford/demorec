"""High-level vim primitives for code review demos.

Provides Open, Highlight, and Close commands that handle all the vim
complexity internally, including:
- Installing vim if not present
- Opening files with line numbers enabled
- Calculating proper scroll positions based on terminal rows
- Visual line selection for highlights
- Clean exit

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


def ensure_vim_installed() -> list[tuple[str, float]]:
    """Return commands to install vim if not present.
    
    Returns list of (keys_to_type, delay_after) tuples.
    """
    # Check if vim exists - if not, install it
    # We use 'command -v' which is POSIX and works in bash
    commands = []
    
    # Install vim if needed (works on Debian/Ubuntu)
    # This is a single command that checks and installs atomically
    install_cmd = "command -v vim >/dev/null || { echo 'Installing vim...' && sudo apt-get update -qq && sudo apt-get install -y -qq vim; }"
    commands.append((install_cmd, 0))
    commands.append(("ENTER", 3.0))  # Wait for potential install
    
    return commands


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
    
    # Open file in vim
    commands.append((f"vim {file_path}", 0))
    commands.append(("ENTER", 1.0))  # Wait for vim to load
    
    # Enable line numbers
    commands.append((":set number", 0))
    commands.append(("ENTER", 0.3))
    
    return commands


def generate_highlight_commands(
    line_range: str, 
    state: VimState,
    centering: str = "auto"
) -> list[tuple[str, float]]:
    """Generate vim commands to highlight a range of lines.
    
    Args:
        line_range: Line range like "6-8" or "27-35"
        state: VimState with current position and terminal info
        centering: How to center the selection:
            - "auto": Automatically choose best centering
            - "top": Use zt (selection at top)
            - "center": Use zz (selection centered)
            - "bottom": Use zb (selection at bottom)
            
    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    # Parse line range
    if "-" in line_range:
        start_line, end_line = map(int, line_range.split("-"))
    else:
        start_line = end_line = int(line_range)
    
    num_lines = end_line - start_line + 1
    commands = []
    
    # Exit visual mode if we're in it
    if state.in_visual_mode:
        commands.append(("ESCAPE", 0.2))
        state.in_visual_mode = False
    
    # Calculate the best line to jump to for centering
    # We want the selection visible in the viewport
    available_rows = state.terminal_rows - 2  # Account for status line + some margin
    
    if centering == "auto":
        if num_lines <= available_rows // 2:
            # Small selection - center it
            center_line = (start_line + end_line) // 2
            commands.append((f"{center_line}G", 0.2))
            commands.append(("zz", 0.3))  # Center this line
        else:
            # Large selection - put start at top
            commands.append((f"{start_line}G", 0.2))
            commands.append(("zt", 0.3))  # Scroll to top
    elif centering == "top":
        commands.append((f"{start_line}G", 0.2))
        commands.append(("zt", 0.3))
    elif centering == "center":
        center_line = (start_line + end_line) // 2
        commands.append((f"{center_line}G", 0.2))
        commands.append(("zz", 0.3))
    elif centering == "bottom":
        commands.append((f"{end_line}G", 0.2))
        commands.append(("zb", 0.3))
    
    # Start visual line mode from the start of selection
    commands.append((f"{start_line}G", 0.2))
    commands.append(("V", 0.2))  # Visual line mode
    state.in_visual_mode = True
    
    # Extend to end of selection (if more than one line)
    if end_line > start_line:
        commands.append((f"{end_line}G", 0.3))
    
    state.current_line = end_line
    
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


def generate_goto_commands(line: int, state: VimState, centering: str = "center") -> list[tuple[str, float]]:
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
    """
    
    def __init__(self, terminal_rows: int = 24):
        self.state = VimState(terminal_rows=terminal_rows)
        self._vim_checked = False
    
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
        
        # Ensure vim is installed (only check once per session)
        if cmd_name == "Open" and not self._vim_checked:
            commands.extend(ensure_vim_installed())
            self._vim_checked = True
        
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
