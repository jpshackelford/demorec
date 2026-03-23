"""Unit tests for VimCommandExpander and vim primitives."""

import pytest
from unittest.mock import patch

from demorec.modes.vim import (
    VimState,
    VimCommandExpander,
    VimNotFoundError,
    check_vim_available,
)


class TestVimNotFoundError:
    """Test fail-fast vim detection."""
    
    def test_check_vim_available_raises_when_not_found(self):
        """Should raise VimNotFoundError with clear message when vim not in PATH."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(VimNotFoundError) as exc_info:
                check_vim_available()
            
            error_msg = str(exc_info.value)
            assert "vim is not installed" in error_msg
            assert "apt-get install vim" in error_msg
            assert "brew install vim" in error_msg
            assert "dnf install vim" in error_msg
    
    def test_check_vim_available_passes_when_found(self):
        """Should not raise when vim is found in PATH."""
        with patch("shutil.which", return_value="/usr/bin/vim"):
            # Should not raise
            check_vim_available()
    
    def test_check_vim_available_real_system(self):
        """Test actual vim availability on the system (no mocking).
        
        This test verifies the real code path works, not just mocks.
        If vim is installed, it should pass. If not, it should raise
        VimNotFoundError with helpful install instructions.
        """
        import shutil
        vim_path = shutil.which("vim")
        
        if vim_path:
            # Vim is installed - check_vim_available should succeed
            check_vim_available()  # Should not raise
        else:
            # Vim is not installed - should raise with install instructions
            with pytest.raises(VimNotFoundError) as exc_info:
                check_vim_available()
            assert "apt-get install vim" in str(exc_info.value)


class TestVimState:
    """Test VimState dataclass."""
    
    def test_default_state(self):
        """Test default state values."""
        state = VimState()
        assert state.file_path is None
        assert state.current_line == 1
        assert state.terminal_rows == 24
        assert state.in_visual_mode is False
    
    def test_custom_state(self):
        """Test state with custom values."""
        state = VimState(terminal_rows=30)
        assert state.terminal_rows == 30


class TestVimStateOpen:
    """Test VimState.open() method."""
    
    def test_opens_file_with_line_numbers(self):
        """Should generate commands to open file and enable line numbers."""
        state = VimState()
        commands = state.open("src/api.py")
        
        # Should have: vim command, ENTER, :set number, ENTER
        assert len(commands) == 4
        assert commands[0] == ("vim src/api.py", 0)
        assert commands[1] == ("ENTER", 1.0)
        assert commands[2] == (":set number", 0)
        assert commands[3] == ("ENTER", 0.3)
    
    def test_updates_state(self):
        """Should update state after opening file."""
        state = VimState()
        state.open("test.py")
        
        assert state.file_path == "test.py"
        assert state.current_line == 1
        assert state.in_visual_mode is False


class TestVimStateHighlight:
    """Test VimState.highlight() method."""
    
    def test_single_line_highlight(self):
        """Test highlighting a single line."""
        state = VimState(terminal_rows=24)
        commands = state.highlight("10")
        
        # Should navigate to line and enter visual mode
        assert any("10G" in cmd[0] for cmd in commands)
        assert any("V" in cmd[0] for cmd in commands)
    
    def test_range_highlight(self):
        """Test highlighting a range of lines."""
        state = VimState(terminal_rows=30)
        commands = state.highlight("6-8")
        
        # Should navigate to start, enter visual mode, extend to end
        assert any("6G" in cmd[0] for cmd in commands)
        assert any("V" in cmd[0] for cmd in commands)
        assert any("8G" in cmd[0] for cmd in commands)
    
    def test_updates_visual_mode_state(self):
        """Should set in_visual_mode to True after highlight."""
        state = VimState()
        state.highlight("10-20")
        
        assert state.in_visual_mode is True
        assert state.current_line == 20
    
    def test_exits_visual_mode_if_already_in_it(self):
        """Should exit visual mode before new highlight."""
        state = VimState()
        state.in_visual_mode = True
        
        commands = state.highlight("5-10")
        
        # First command should be ESCAPE
        assert commands[0] == ("ESCAPE", 0.2)
    
    def test_centering_auto_small_selection(self):
        """Auto centering should use zz for small selections."""
        state = VimState(terminal_rows=30)
        commands = state.highlight("10-12", centering="auto")
        
        # Small selection (3 lines) should use zz (center)
        assert any("zz" in cmd[0] for cmd in commands)
    
    def test_centering_auto_large_selection(self):
        """Auto centering should use zt for large selections."""
        state = VimState(terminal_rows=24)
        commands = state.highlight("10-30", centering="auto")
        
        # Large selection (21 lines) should use zt (top)
        assert any("zt" in cmd[0] for cmd in commands)
    
    def test_centering_explicit_top(self):
        """Explicit top centering should use zt."""
        state = VimState()
        commands = state.highlight("15-20", centering="top")
        
        assert any("zt" in cmd[0] for cmd in commands)
    
    def test_centering_explicit_center(self):
        """Explicit center centering should use zz."""
        state = VimState()
        commands = state.highlight("15-20", centering="center")
        
        assert any("zz" in cmd[0] for cmd in commands)
    
    def test_centering_explicit_bottom(self):
        """Explicit bottom centering should use zb."""
        state = VimState()
        commands = state.highlight("15-20", centering="bottom")
        
        assert any("zb" in cmd[0] for cmd in commands)


class TestVimStateClose:
    """Test VimState.close() method."""
    
    def test_close_from_normal_mode(self):
        """Should generate :q! command to exit."""
        state = VimState()
        commands = state.close()
        
        assert any(":q!" in cmd[0] for cmd in commands)
        assert any("ENTER" in cmd[0] for cmd in commands)
    
    def test_close_from_visual_mode(self):
        """Should exit visual mode before closing."""
        state = VimState()
        state.in_visual_mode = True
        
        commands = state.close()
        
        # Should start with ESCAPE to exit visual mode
        assert commands[0] == ("ESCAPE", 0.2)
    
    def test_clears_state(self):
        """Should clear file_path after close."""
        state = VimState()
        state.file_path = "test.py"
        state.current_line = 50
        
        state.close()
        
        assert state.file_path is None
        assert state.current_line == 1


class TestVimStateGoto:
    """Test VimState.goto() method."""
    
    def test_goto_with_center(self):
        """Should generate goto and zz for center."""
        state = VimState()
        commands = state.goto(25, centering="center")
        
        assert any("25G" in cmd[0] for cmd in commands)
        assert any("zz" in cmd[0] for cmd in commands)
    
    def test_goto_updates_current_line(self):
        """Should update current_line in state."""
        state = VimState()
        state.goto(42)
        
        assert state.current_line == 42


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
        with patch("demorec.modes.vim.check_vim_available"):
            expander = VimCommandExpander()
            commands = expander.expand_command("Open", ["test.py"])
            
            assert len(commands) > 0
            assert any("vim test.py" in cmd[0] for cmd in commands)
    
    def test_expand_highlight_command(self):
        """Should expand Highlight command to keystrokes."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Highlight", ["10-20"])
        
        assert len(commands) > 0
        assert any("V" in cmd[0] for cmd in commands)
    
    def test_expand_close_command(self):
        """Should expand Close command to keystrokes."""
        expander = VimCommandExpander()
        commands = expander.expand_command("Close", [])
        
        assert len(commands) > 0
        assert any(":q!" in cmd[0] for cmd in commands)
    
    def test_set_terminal_rows(self):
        """Should update terminal rows for calculations."""
        expander = VimCommandExpander(terminal_rows=24)
        assert expander.state.terminal_rows == 24
        
        expander.set_terminal_rows(40)
        assert expander.state.terminal_rows == 40
    
    def test_vim_check_only_on_first_open(self):
        """Should only check vim availability on first Open command."""
        with patch("demorec.modes.vim.check_vim_available") as mock_check:
            expander = VimCommandExpander()
            
            expander.expand_command("Open", ["file1.py"])
            expander.expand_command("Open", ["file2.py"])
            
            # Should only be called once
            assert mock_check.call_count == 1
    
    def test_state_persists_across_commands(self):
        """State should persist across command expansions."""
        with patch("demorec.modes.vim.check_vim_available"):
            expander = VimCommandExpander()
            
            expander.expand_command("Open", ["test.py"])
            assert expander.state.file_path == "test.py"
            
            expander.expand_command("Highlight", ["10-20"])
            assert expander.state.in_visual_mode is True
            assert expander.state.current_line == 20
            
            expander.expand_command("Close", [])
            assert expander.state.file_path is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
