"""High-level vim primitives for code review demos.

Provides Open, Highlight, and Close commands that handle all the vim
complexity internally, including:
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


class VimNotFoundError(Exception):
    """Raised when vim is not installed."""
    pass


def check_vim_available() -> None:
    """Check if vim is available on the system.
    
    Raises:
        VimNotFoundError: If vim is not found in PATH with instructions to install.
    """
    if shutil.which("vim") is None:
        raise VimNotFoundError(
            "vim is not installed or not in PATH.\n\n"
            "To install vim:\n"
            "  Ubuntu/Debian: sudo apt-get install vim\n"
            "  macOS:         brew install vim\n"
            "  Fedora/RHEL:   sudo dnf install vim\n"
            "  Alpine:        apk add vim\n\n"
            "After installing, re-run your demorec script."
        )


class VimState:
    """Tracks vim session state and generates commands.
    
    This class manages vim state and provides methods that generate keystroke
    commands while updating internal state. All mutations are explicit through
    method calls.
    """
    
    def __init__(self, terminal_rows: int = 24):
        self.file_path: str | None = None
        self.current_line: int = 1
        self.terminal_rows: int = terminal_rows
        self.in_visual_mode: bool = False
        self.file_total_lines: int | None = None
    
    def open(self, file_path: str) -> list[tuple[str, float]]:
        """Generate commands to open a file in vim with line numbers.
        
        Updates state: file_path, current_line, in_visual_mode
        
        Args:
            file_path: Path to the file to open
            
        Returns:
            List of (keys_to_type, delay_after) tuples
        """
        self.file_path = file_path
        self.current_line = 1
        self.in_visual_mode = False
        
        return [
            (f"vim {file_path}", 0),
            ("ENTER", 1.0),  # Wait for vim to load
            (":set number", 0),
            ("ENTER", 0.3),
        ]
    
    def highlight(self, line_range: str, centering: str = "auto") -> list[tuple[str, float]]:
        """Generate vim commands to highlight a range of lines.
        
        Updates state: in_visual_mode, current_line
        
        Args:
            line_range: Line range like "6-8" or "27-35" or single line "10"
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
        commands: list[tuple[str, float]] = []
        
        # Exit visual mode if we're in it
        if self.in_visual_mode:
            commands.append(("ESCAPE", 0.2))
            self.in_visual_mode = False
        
        # Calculate centering strategy
        available_rows = self.terminal_rows - 2  # Account for status line + margin
        
        # Normalize "auto" to a concrete centering strategy
        effective_centering = centering
        if centering == "auto":
            effective_centering = "center" if num_lines <= available_rows // 2 else "top"
        
        # Apply centering
        commands.extend(self._centering_commands(start_line, end_line, effective_centering))
        
        # Start visual line mode from the start of selection
        commands.append((f"{start_line}G", 0.2))
        commands.append(("V", 0.2))  # Visual line mode
        self.in_visual_mode = True
        
        # Extend to end of selection (if more than one line)
        if end_line > start_line:
            commands.append((f"{end_line}G", 0.3))
        
        self.current_line = end_line
        return commands
    
    def _centering_commands(self, start_line: int, end_line: int, centering: str) -> list[tuple[str, float]]:
        """Generate centering commands for a line range."""
        if centering == "top":
            return [(f"{start_line}G", 0.2), ("zt", 0.3)]
        elif centering == "center":
            center_line = (start_line + end_line) // 2
            return [(f"{center_line}G", 0.2), ("zz", 0.3)]
        elif centering == "bottom":
            return [(f"{end_line}G", 0.2), ("zb", 0.3)]
        return []
    
    def close(self) -> list[tuple[str, float]]:
        """Generate commands to cleanly exit vim.
        
        Updates state: in_visual_mode, file_path, current_line
        
        Returns:
            List of (keys_to_type, delay_after) tuples
        """
        commands: list[tuple[str, float]] = []
        
        # Exit visual mode if needed
        if self.in_visual_mode:
            commands.append(("ESCAPE", 0.2))
            self.in_visual_mode = False
        
        # Quit without saving
        commands.append(("ESCAPE", 0.2))  # Ensure we're in normal mode
        commands.append((":q!", 0))
        commands.append(("ENTER", 0.5))
        
        # Clear state
        self.file_path = None
        self.current_line = 1
        
        return commands
    
    def goto(self, line: int, centering: str = "center") -> list[tuple[str, float]]:
        """Generate commands to go to a specific line.
        
        Updates state: in_visual_mode, current_line
        
        Args:
            line: Line number to go to
            centering: How to position the line ("top", "center", "bottom")
            
        Returns:
            List of (keys_to_type, delay_after) tuples
        """
        commands: list[tuple[str, float]] = []
        
        # Exit visual mode if needed
        if self.in_visual_mode:
            commands.append(("ESCAPE", 0.2))
            self.in_visual_mode = False
        
        # Go to line
        commands.append((f"{line}G", 0.2))
        
        # Center appropriately
        if centering == "top":
            commands.append(("zt", 0.3))
        elif centering == "center":
            commands.append(("zz", 0.3))
        elif centering == "bottom":
            commands.append(("zb", 0.3))
        
        self.current_line = line
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
            
        Raises:
            VimNotFoundError: If vim is not installed (checked on first Open command)
        """
        # Check vim is available (only once per session, fail fast with clear message)
        if cmd_name == "Open" and not self._vim_checked:
            check_vim_available()
            self._vim_checked = True
        
        # Dispatch to VimState methods (mutations are explicit in method names)
        if cmd_name == "Open" and cmd_args:
            return self.state.open(cmd_args[0])
        elif cmd_name == "Highlight" and cmd_args:
            centering = cmd_args[1] if len(cmd_args) > 1 else "auto"
            return self.state.highlight(cmd_args[0], centering)
        elif cmd_name == "Close":
            return self.state.close()
        elif cmd_name == "Goto" and cmd_args:
            centering = cmd_args[1] if len(cmd_args) > 1 else "center"
            return self.state.goto(int(cmd_args[0]), centering)
        
        return []
    
    def is_vim_command(self, cmd_name: str) -> bool:
        """Check if a command is a high-level vim command."""
        return cmd_name in ("Open", "Highlight", "Close", "Goto")
