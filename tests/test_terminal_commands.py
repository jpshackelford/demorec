"""Unit tests for terminal commands and themes.

Tests cover:
- THEMES dictionary structure
- TERMINAL_COMMANDS dispatch table
- Individual command handlers
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from demorec.modes.terminal_commands import (
    THEMES,
    TERMINAL_COMMANDS,
    _cmd_type,
    _cmd_enter,
    _cmd_run,
    _cmd_sleep,
    _cmd_ctrl_c,
    _cmd_ctrl_d,
    _cmd_tab,
    _cmd_up,
    _cmd_down,
    _cmd_backspace,
    _cmd_escape,
    _cmd_space,
    _cmd_clear,
)
from demorec.parser import Command


class TestThemes:
    """Test THEMES dictionary."""

    def test_dracula_theme_exists(self):
        """Dracula theme should exist."""
        assert "dracula" in THEMES

    def test_github_dark_theme_exists(self):
        """GitHub dark theme should exist."""
        assert "github-dark" in THEMES

    def test_theme_has_required_colors(self):
        """Themes should have required color keys."""
        required_keys = [
            "background",
            "foreground",
            "cursor",
            "black",
            "red",
            "green",
            "yellow",
            "blue",
            "magenta",
            "cyan",
            "white",
        ]
        for theme_name, theme in THEMES.items():
            for key in required_keys:
                assert key in theme, f"{theme_name} missing {key}"

    def test_colors_are_hex(self):
        """Theme colors should be hex values."""
        for theme_name, theme in THEMES.items():
            for key, value in theme.items():
                assert value.startswith("#"), f"{theme_name}.{key} is not hex: {value}"


class TestTerminalCommands:
    """Test TERMINAL_COMMANDS dispatch table."""

    def test_has_basic_commands(self):
        """Should have basic terminal commands."""
        assert "Type" in TERMINAL_COMMANDS
        assert "Enter" in TERMINAL_COMMANDS
        assert "Run" in TERMINAL_COMMANDS
        assert "Sleep" in TERMINAL_COMMANDS
        assert "Clear" in TERMINAL_COMMANDS

    def test_has_ctrl_commands(self):
        """Should have Ctrl key combinations."""
        assert "Ctrl+C" in TERMINAL_COMMANDS
        assert "Ctrl+D" in TERMINAL_COMMANDS
        assert "Ctrl+L" in TERMINAL_COMMANDS
        assert "Ctrl+Z" in TERMINAL_COMMANDS

    def test_has_navigation_commands(self):
        """Should have navigation commands."""
        assert "Tab" in TERMINAL_COMMANDS
        assert "Up" in TERMINAL_COMMANDS
        assert "Down" in TERMINAL_COMMANDS
        assert "Backspace" in TERMINAL_COMMANDS
        assert "Escape" in TERMINAL_COMMANDS
        assert "Space" in TERMINAL_COMMANDS

    def test_all_handlers_are_callable(self):
        """All command handlers should be callable."""
        for name, handler in TERMINAL_COMMANDS.items():
            assert callable(handler), f"{name} handler is not callable"


class TestCommandHandlers:
    """Test individual command handlers."""

    @pytest.fixture
    def mock_page(self):
        """Create mock page object."""
        page = AsyncMock()
        page.keyboard = AsyncMock()
        page.keyboard.press = AsyncMock()
        page.keyboard.type = AsyncMock()
        return page

    @pytest.fixture
    def mock_recorder(self):
        """Create mock recorder object."""
        recorder = MagicMock()
        recorder._send_keys = AsyncMock()
        return recorder

    @pytest.mark.asyncio
    async def test_cmd_type(self, mock_recorder, mock_page):
        """Type command should send keys."""
        cmd = Command("Type", ["hello world"])
        await _cmd_type(mock_recorder, mock_page, cmd)
        mock_recorder._send_keys.assert_called_once_with(mock_page, "hello world")

    @pytest.mark.asyncio
    async def test_cmd_type_no_args(self, mock_recorder, mock_page):
        """Type command with no args should not send anything."""
        cmd = Command("Type", [])
        await _cmd_type(mock_recorder, mock_page, cmd)
        mock_recorder._send_keys.assert_not_called()

    @pytest.mark.asyncio
    async def test_cmd_enter(self, mock_recorder, mock_page):
        """Enter command should press Enter key."""
        cmd = Command("Enter", [])
        await _cmd_enter(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Enter")

    @pytest.mark.asyncio
    async def test_cmd_run(self, mock_recorder, mock_page):
        """Run command should type and press enter."""
        cmd = Command("Run", ["ls -la"])
        await _cmd_run(mock_recorder, mock_page, cmd)
        mock_recorder._send_keys.assert_called_once_with(mock_page, "ls -la")
        mock_page.keyboard.press.assert_called_with("Enter")

    @pytest.mark.asyncio
    async def test_cmd_run_with_wait(self, mock_recorder, mock_page):
        """Run command with wait time should work."""
        cmd = Command("Run", ["long_command", "0.1s"])
        await _cmd_run(mock_recorder, mock_page, cmd)
        mock_recorder._send_keys.assert_called_once()
        mock_page.keyboard.press.assert_called_with("Enter")

    @pytest.mark.asyncio
    async def test_cmd_ctrl_c(self, mock_recorder, mock_page):
        """Ctrl+C command should press Control+c."""
        cmd = Command("Ctrl+C", [])
        await _cmd_ctrl_c(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Control+c")

    @pytest.mark.asyncio
    async def test_cmd_ctrl_d(self, mock_recorder, mock_page):
        """Ctrl+D command should press Control+d."""
        cmd = Command("Ctrl+D", [])
        await _cmd_ctrl_d(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Control+d")

    @pytest.mark.asyncio
    async def test_cmd_tab(self, mock_recorder, mock_page):
        """Tab command should press Tab key."""
        cmd = Command("Tab", [])
        await _cmd_tab(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Tab")

    @pytest.mark.asyncio
    async def test_cmd_up(self, mock_recorder, mock_page):
        """Up command should press ArrowUp key."""
        cmd = Command("Up", [])
        await _cmd_up(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("ArrowUp")

    @pytest.mark.asyncio
    async def test_cmd_down(self, mock_recorder, mock_page):
        """Down command should press ArrowDown key."""
        cmd = Command("Down", [])
        await _cmd_down(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("ArrowDown")

    @pytest.mark.asyncio
    async def test_cmd_backspace(self, mock_recorder, mock_page):
        """Backspace command should press Backspace key."""
        cmd = Command("Backspace", [])
        await _cmd_backspace(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Backspace")

    @pytest.mark.asyncio
    async def test_cmd_backspace_multiple(self, mock_recorder, mock_page):
        """Backspace command with count should press multiple times."""
        cmd = Command("Backspace", ["3"])
        await _cmd_backspace(mock_recorder, mock_page, cmd)
        assert mock_page.keyboard.press.call_count == 3

    @pytest.mark.asyncio
    async def test_cmd_escape(self, mock_recorder, mock_page):
        """Escape command should press Escape key."""
        cmd = Command("Escape", [])
        await _cmd_escape(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Escape")

    @pytest.mark.asyncio
    async def test_cmd_space(self, mock_recorder, mock_page):
        """Space command should press Space key."""
        cmd = Command("Space", [])
        await _cmd_space(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Space")

    @pytest.mark.asyncio
    async def test_cmd_clear(self, mock_recorder, mock_page):
        """Clear command should press Ctrl+L."""
        cmd = Command("Clear", [])
        await _cmd_clear(mock_recorder, mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Control+l")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
