"""Unit tests for VimCommandExpander and vim primitives.

Tests cover:
- VimState dataclass
- Standalone vim command generators (generate_open_commands, etc.)
- Helper functions (_parse_line_range, _centering_commands, etc.)
- VimCommandExpander class
- Preflight checks (vim availability)
"""

import pytest
from unittest.mock import patch, MagicMock

from demorec.modes.vim import (
    VimState,
    VimCommandExpander,
    check_vim_installed,
    preflight_check,
    generate_open_commands,
    generate_highlight_commands,
    generate_close_commands,
    generate_goto_commands,
    _parse_line_range,
    _centering_commands,
    _auto_centering,
    _fixed_centering,
    _visual_select_commands,
    _exit_visual_if_needed,
    _get_centering_cmd,
)


class TestVimState:
    """Test VimState dataclass."""

    def test_default_state(self):
        """Test default state values."""
        state = VimState()
        assert state.file_path is None
        assert state.current_line == 1
        assert state.terminal_rows == 24
        assert state.in_visual_mode is False
        assert state.file_total_lines is None

    def test_custom_state(self):
        """Test state with custom values."""
        state = VimState(terminal_rows=30, current_line=50)
        assert state.terminal_rows == 30
        assert state.current_line == 50


class TestCheckVimInstalled:
    """Test vim availability checking."""

    def test_returns_true_when_vim_found(self):
        """Should return True when vim is in PATH."""
        with patch("shutil.which", return_value="/usr/bin/vim"):
            assert check_vim_installed() is True

    def test_returns_false_when_vim_not_found(self):
        """Should return False when vim is not in PATH."""
        with patch("shutil.which", return_value=None):
            assert check_vim_installed() is False


class TestPreflightCheck:
    """Test preflight check function."""

    def test_returns_empty_when_vim_available(self):
        """Should return empty list when vim is available."""
        with patch("demorec.modes.vim.check_vim_installed", return_value=True):
            errors = preflight_check()
            assert errors == []

    def test_returns_error_when_vim_unavailable(self):
        """Should return error message when vim is unavailable."""
        with patch("demorec.modes.vim.check_vim_installed", return_value=False):
            errors = preflight_check()
            assert len(errors) == 1
            assert "vim is not installed" in errors[0]

    def test_error_includes_install_instructions(self):
        """Should include multi-platform install instructions."""
        with patch("demorec.modes.vim.check_vim_installed", return_value=False):
            errors = preflight_check()
            assert "apt-get" in errors[0]  # Ubuntu/Debian
            assert "brew" in errors[0]  # macOS
            assert "dnf" in errors[0]  # Fedora/RHEL


class TestParseLineRange:
    """Test _parse_line_range helper function."""

    def test_single_line(self):
        """Should parse single line number."""
        assert _parse_line_range("10") == (10, 10)
        assert _parse_line_range("1") == (1, 1)
        assert _parse_line_range("100") == (100, 100)

    def test_line_range(self):
        """Should parse line range."""
        assert _parse_line_range("6-8") == (6, 8)
        assert _parse_line_range("1-100") == (1, 100)
        assert _parse_line_range("27-35") == (27, 35)


class TestCenteringCommands:
    """Test centering command generation."""

    def test_auto_centering_small_selection(self):
        """Auto centering should use zz for small selections."""
        commands = _auto_centering(10, 12, 30)  # positional: start, end, rows
        # Center line should be 11
        assert any("11G" in cmd[0] for cmd in commands)
        assert any("zz" in cmd[0] for cmd in commands)

    def test_auto_centering_large_selection(self):
        """Auto centering should use zt for large selections."""
        # 21 lines is > half of available rows (24-2=22)
        commands = _auto_centering(10, 30, 24)  # positional: start, end, rows
        assert any("10G" in cmd[0] for cmd in commands)
        assert any("zt" in cmd[0] for cmd in commands)

    def test_fixed_centering_top(self):
        """Fixed top centering should use zt."""
        commands = _fixed_centering(15, 20, "top")
        assert any("15G" in cmd[0] for cmd in commands)
        assert any("zt" in cmd[0] for cmd in commands)

    def test_fixed_centering_center(self):
        """Fixed center centering should use zz."""
        commands = _fixed_centering(15, 20, "center")
        # Center line should be 17
        assert any("17G" in cmd[0] for cmd in commands)
        assert any("zz" in cmd[0] for cmd in commands)

    def test_fixed_centering_bottom(self):
        """Fixed bottom centering should use zb."""
        commands = _fixed_centering(15, 20, "bottom")
        assert any("20G" in cmd[0] for cmd in commands)
        assert any("zb" in cmd[0] for cmd in commands)

    def test_centering_commands_auto(self):
        """Test _centering_commands with auto mode."""
        commands = _centering_commands(10, 12, 30, "auto")
        assert len(commands) > 0

    def test_centering_commands_explicit(self):
        """Test _centering_commands with explicit mode."""
        commands = _centering_commands(10, 12, 30, "top")
        assert any("zt" in cmd[0] for cmd in commands)


class TestVisualSelectCommands:
    """Test visual selection command generation."""

    def test_single_line_selection(self):
        """Single line selection should not add extra goto."""
        commands = _visual_select_commands(10, 10)
        assert ("10G", 0.2) in commands
        assert ("V", 0.2) in commands
        assert len(commands) == 2

    def test_range_selection(self):
        """Range selection should add goto end line."""
        commands = _visual_select_commands(10, 20)
        assert ("10G", 0.2) in commands
        assert ("V", 0.2) in commands
        assert ("20G", 0.3) in commands
        assert len(commands) == 3


class TestExitVisualIfNeeded:
    """Test _exit_visual_if_needed helper."""

    def test_exits_visual_mode(self):
        """Should return ESCAPE if in visual mode."""
        state = VimState(in_visual_mode=True)
        commands = _exit_visual_if_needed(state)
        assert commands == [("ESCAPE", 0.2)]
        assert state.in_visual_mode is False

    def test_no_op_if_not_in_visual(self):
        """Should return empty list if not in visual mode."""
        state = VimState(in_visual_mode=False)
        commands = _exit_visual_if_needed(state)
        assert commands == []


class TestGetCenteringCmd:
    """Test _get_centering_cmd helper."""

    def test_top(self):
        assert _get_centering_cmd("top") == [("zt", 0.3)]

    def test_center(self):
        assert _get_centering_cmd("center") == [("zz", 0.3)]

    def test_bottom(self):
        assert _get_centering_cmd("bottom") == [("zb", 0.3)]

    def test_invalid(self):
        assert _get_centering_cmd("invalid") == []


class TestGenerateOpenCommands:
    """Test generate_open_commands function."""

    def test_opens_file_with_vim_flags(self):
        """Should use vim -i NONE +1 for clean start."""
        state = VimState()
        commands = generate_open_commands("src/api.py", state)
        assert any("vim -i NONE +1 src/api.py" in cmd[0] for cmd in commands)

    def test_enables_line_numbers(self):
        """Should include :set number command."""
        state = VimState()
        commands = generate_open_commands("test.py", state)
        assert any(":set number" in cmd[0] for cmd in commands)

    def test_includes_enter_commands(self):
        """Should include ENTER to execute commands."""
        state = VimState()
        commands = generate_open_commands("test.py", state)
        enter_commands = [c for c in commands if c[0] == "ENTER"]
        assert len(enter_commands) >= 2

    def test_updates_state(self):
        """Should update state after opening file."""
        state = VimState(current_line=50, in_visual_mode=True)
        generate_open_commands("test.py", state)
        assert state.file_path == "test.py"
        assert state.current_line == 1
        assert state.in_visual_mode is False


class TestGenerateHighlightCommands:
    """Test generate_highlight_commands function."""

    def test_single_line_highlight(self):
        """Should highlight a single line."""
        state = VimState(terminal_rows=24)
        commands = generate_highlight_commands("10", state)
        assert any("10G" in cmd[0] for cmd in commands)
        assert any("V" in cmd[0] for cmd in commands)

    def test_range_highlight(self):
        """Should highlight a range of lines."""
        state = VimState(terminal_rows=30)
        commands = generate_highlight_commands("6-8", state)
        assert any("6G" in cmd[0] for cmd in commands)
        assert any("V" in cmd[0] for cmd in commands)
        assert any("8G" in cmd[0] for cmd in commands)

    def test_updates_visual_mode_state(self):
        """Should set in_visual_mode to True."""
        state = VimState()
        generate_highlight_commands("10-20", state)
        assert state.in_visual_mode is True
        assert state.current_line == 20

    def test_exits_visual_mode_if_already_in_it(self):
        """Should exit visual mode before new highlight."""
        state = VimState(in_visual_mode=True)
        commands = generate_highlight_commands("5-10", state)
        assert commands[0] == ("ESCAPE", 0.2)

    def test_centering_explicit_top(self):
        """Explicit top centering should use zt."""
        state = VimState()
        commands = generate_highlight_commands("15-20", state, centering="top")
        assert any("zt" in cmd[0] for cmd in commands)


class TestGenerateCloseCommands:
    """Test generate_close_commands function."""

    def test_close_from_normal_mode(self):
        """Should generate :q! command to exit."""
        state = VimState()
        commands = generate_close_commands(state)
        assert any(":q!" in cmd[0] for cmd in commands)
        assert any(cmd[0] == "ENTER" for cmd in commands)

    def test_close_from_visual_mode(self):
        """Should exit visual mode before closing."""
        state = VimState(in_visual_mode=True)
        commands = generate_close_commands(state)
        assert commands[0] == ("ESCAPE", 0.2)

    def test_clears_state(self):
        """Should clear file_path after close."""
        state = VimState(file_path="test.py", current_line=50)
        generate_close_commands(state)
        assert state.file_path is None
        assert state.current_line == 1


class TestGenerateGotoCommands:
    """Test generate_goto_commands function."""

    def test_goto_with_center(self):
        """Should generate goto and zz for center."""
        state = VimState()
        commands = generate_goto_commands(25, state, centering="center")
        assert any("25G" in cmd[0] for cmd in commands)
        assert any("zz" in cmd[0] for cmd in commands)

    def test_goto_updates_current_line(self):
        """Should update current_line in state."""
        state = VimState()
        generate_goto_commands(42, state)
        assert state.current_line == 42

    def test_goto_exits_visual_mode(self):
        """Should exit visual mode if in it."""
        state = VimState(in_visual_mode=True)
        commands = generate_goto_commands(10, state)
        assert ("ESCAPE", 0.2) in commands


class TestVimCommandExpander:
    """Test VimCommandExpander class."""

    def test_is_vim_command(self):
        """Should correctly identify vim commands."""
        expander = VimCommandExpander()
        assert expander.is_vim_command("Open") is True
        assert expander.is_vim_command("Highlight") is True
        assert expander.is_vim_command("Close") is True
        assert expander.is_vim_command("Goto") is True
        assert expander.is_vim_command("Type") is False
        assert expander.is_vim_command("Enter") is False

    def test_expand_open_command(self):
        """Should expand Open command to keystrokes."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Open", ["test.py"])
        assert len(commands) > 0
        assert any("vim" in cmd[0] and "test.py" in cmd[0] for cmd in commands)

    def test_expand_open_empty_args(self):
        """Should return empty list for Open with no args."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Open", [])
        assert commands == []

    def test_expand_highlight_command(self):
        """Should expand Highlight command to keystrokes."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Highlight", ["10-20"])
        assert len(commands) > 0
        assert any("V" in cmd[0] for cmd in commands)

    def test_expand_highlight_empty_args(self):
        """Should return empty list for Highlight with no args."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Highlight", [])
        assert commands == []

    def test_expand_close_command(self):
        """Should expand Close command to keystrokes."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Close", [])
        assert len(commands) > 0
        assert any(":q!" in cmd[0] for cmd in commands)

    def test_expand_goto_command(self):
        """Should expand Goto command to keystrokes."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Goto", ["50"])
        assert len(commands) > 0
        assert any("50G" in cmd[0] for cmd in commands)

    def test_expand_goto_empty_args(self):
        """Should return empty list for Goto with no args."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Goto", [])
        assert commands == []

    def test_expand_unknown_command(self):
        """Should return empty list for unknown commands."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Unknown", ["arg"])
        assert commands == []

    def test_set_terminal_rows(self):
        """Should update terminal rows for calculations."""
        expander = VimCommandExpander(terminal_rows=24)
        assert expander.state.terminal_rows == 24
        expander.set_terminal_rows(40)
        assert expander.state.terminal_rows == 40

    def test_state_persists_across_commands(self):
        """State should persist across command expansions."""
        expander = VimCommandExpander()
        expander.expand_command("Open", ["test.py"])
        assert expander.state.file_path == "test.py"

        expander.expand_command("Highlight", ["10-20"])
        assert expander.state.in_visual_mode is True
        assert expander.state.current_line == 20

        expander.expand_command("Close", [])
        assert expander.state.file_path is None

    def test_highlight_with_centering_arg(self):
        """Should pass centering argument to highlight."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Highlight", ["10-20", "top"])
        assert any("zt" in cmd[0] for cmd in commands)

    def test_goto_with_centering_arg(self):
        """Should pass centering argument to goto."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Goto", ["25", "bottom"])
        assert any("zb" in cmd[0] for cmd in commands)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
