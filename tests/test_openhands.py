"""Unit tests for OpenHandsCommandExpander and OpenHands CLI primitives.

Tests cover:
- OpenHandsState dataclass
- Preflight checks (LLM configuration)
- Standalone command generators (generate_install_commands, etc.)
- OpenHandsCommandExpander class
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from demorec.modes.openhands import (
    OpenHandsState,
    OpenHandsCommandExpander,
    check_openhands_installed,
    check_llm_configured,
    preflight_check,
    generate_install_commands,
    generate_start_commands,
    generate_prompt_commands,
    generate_multiline_commands,
    generate_command_commands,
    generate_palette_commands,
    generate_quit_commands,
)


class TestOpenHandsState:
    """Test OpenHandsState dataclass."""

    def test_default_state(self):
        """Test default state values."""
        state = OpenHandsState()
        assert state.running is False

    def test_custom_state(self):
        """Test state with custom values."""
        state = OpenHandsState(running=True)
        assert state.running is True


class TestCheckOpenHandsInstalled:
    """Test OpenHands CLI availability checking."""

    def test_returns_true_when_in_path(self):
        """Should return True when openhands is in PATH."""
        with patch("shutil.which", return_value="/usr/local/bin/openhands"):
            assert check_openhands_installed() is True

    def test_returns_true_when_in_local_bin(self):
        """Should return True when openhands is in ~/.local/bin."""
        with patch("shutil.which", return_value=None):
            with patch.object(Path, "exists", return_value=True):
                assert check_openhands_installed() is True

    def test_returns_false_when_not_found(self):
        """Should return False when openhands is not found."""
        with patch("shutil.which", return_value=None):
            with patch.object(Path, "exists", return_value=False):
                assert check_openhands_installed() is False


class TestCheckLlmConfigured:
    """Test LLM configuration checking."""

    def test_returns_true_when_settings_exist(self):
        """Should return True when settings file exists."""
        with patch.object(Path, "exists", return_value=True):
            assert check_llm_configured() is True

    def test_returns_false_when_settings_missing(self):
        """Should return False when settings file doesn't exist."""
        with patch.object(Path, "exists", return_value=False):
            assert check_llm_configured() is False


class TestPreflightCheck:
    """Test preflight check function."""

    def test_returns_empty_when_settings_configured(self):
        """Should return empty list when settings file exists."""
        with patch("demorec.modes.openhands.check_llm_configured", return_value=True):
            errors = preflight_check()
            assert errors == []

    def test_returns_empty_when_env_vars_set(self):
        """Should return empty list when LLM_MODEL and LLM_API_KEY are set."""
        with patch("demorec.modes.openhands.check_llm_configured", return_value=False):
            with patch.dict(os.environ, {"LLM_MODEL": "gpt-4", "LLM_API_KEY": "sk-xxx"}):
                errors = preflight_check()
                assert errors == []

    def test_returns_empty_when_all_env_vars_set(self):
        """Should return empty list when all three env vars are set."""
        with patch("demorec.modes.openhands.check_llm_configured", return_value=False):
            env = {"LLM_MODEL": "gpt-4", "LLM_API_KEY": "sk-xxx", "LLM_BASE_URL": "https://api.openai.com"}
            with patch.dict(os.environ, env, clear=False):
                errors = preflight_check()
                assert errors == []

    def test_returns_error_when_no_config(self):
        """Should return error when neither settings nor env vars are set."""
        with patch("demorec.modes.openhands.check_llm_configured", return_value=False):
            with patch.dict(os.environ, {}, clear=True):
                errors = preflight_check()
                assert len(errors) == 1
                assert "not configured" in errors[0]

    def test_returns_error_when_only_model_set(self):
        """Should return error when only LLM_MODEL is set."""
        with patch("demorec.modes.openhands.check_llm_configured", return_value=False):
            with patch.dict(os.environ, {"LLM_MODEL": "gpt-4"}, clear=True):
                errors = preflight_check()
                assert len(errors) == 1

    def test_returns_error_when_only_api_key_set(self):
        """Should return error when only LLM_API_KEY is set."""
        with patch("demorec.modes.openhands.check_llm_configured", return_value=False):
            with patch.dict(os.environ, {"LLM_API_KEY": "sk-xxx"}, clear=True):
                errors = preflight_check()
                assert len(errors) == 1

    def test_base_url_not_required(self):
        """LLM_BASE_URL should not be required for env var config."""
        with patch("demorec.modes.openhands.check_llm_configured", return_value=False):
            # Only MODEL and API_KEY, no BASE_URL
            with patch.dict(os.environ, {"LLM_MODEL": "gpt-4", "LLM_API_KEY": "sk-xxx"}, clear=True):
                errors = preflight_check()
                assert errors == []


class TestGenerateInstallCommands:
    """Test generate_install_commands function."""

    def test_basic_install(self):
        """Should generate uv tool install command."""
        commands = generate_install_commands()
        assert any("uv tool install openhands" in cmd[0] for cmd in commands)
        assert any("--python 3.12" in cmd[0] for cmd in commands)

    def test_install_with_version(self):
        """Should include version when specified."""
        commands = generate_install_commands("1.14.0")
        assert any("openhands==1.14.0" in cmd[0] for cmd in commands)

    def test_includes_path_export(self):
        """Should include PATH export command."""
        commands = generate_install_commands()
        assert any("PATH" in cmd[0] and ".local/bin" in cmd[0] for cmd in commands)

    def test_includes_enter_commands(self):
        """Should include ENTER to execute commands."""
        commands = generate_install_commands()
        enter_commands = [c for c in commands if c[0] == "ENTER"]
        assert len(enter_commands) >= 1

    def test_has_wait_for_installation(self):
        """Should have delay to wait for installation."""
        commands = generate_install_commands()
        # Should have a significant delay after the install command
        delays = [c[1] for c in commands if "uv tool install" in c[0] or c[0] == "ENTER"]
        assert any(d >= 10.0 for d in delays)


class TestGenerateStartCommands:
    """Test generate_start_commands function."""

    def test_starts_openhands_cli(self):
        """Should generate openhands command."""
        state = OpenHandsState()
        commands = generate_start_commands(state)
        assert any("openhands" in cmd[0] for cmd in commands)

    def test_includes_enter(self):
        """Should include ENTER to execute command."""
        state = OpenHandsState()
        commands = generate_start_commands(state)
        assert ("ENTER", 5.0) in commands

    def test_updates_state(self):
        """Should update state to running."""
        state = OpenHandsState()
        generate_start_commands(state)
        assert state.running is True


class TestGeneratePromptCommands:
    """Test generate_prompt_commands function."""

    def test_types_prompt_text(self):
        """Should generate command to type the prompt."""
        commands = generate_prompt_commands("Tell me a joke")
        assert commands[0][0] == "Tell me a joke"

    def test_submits_with_enter(self):
        """Should submit prompt with ENTER."""
        commands = generate_prompt_commands("Hello")
        assert commands[1][0] == "ENTER"

    def test_default_wait_time(self):
        """Should use default 10s wait time."""
        commands = generate_prompt_commands("Hello")
        assert commands[1][1] == 10.0

    def test_custom_wait_time(self):
        """Should use custom wait time when specified."""
        commands = generate_prompt_commands("Complex task", wait=30.0)
        assert commands[1][1] == 30.0


class TestGenerateMultilineCommands:
    """Test generate_multiline_commands function."""

    def test_enters_multiline_mode(self):
        """Should enter multiline mode with CTRL+L."""
        commands = generate_multiline_commands("Line 1\nLine 2")
        assert commands[0] == ("CTRL+L", 0.3)

    def test_types_each_line(self):
        """Should type each line of the prompt."""
        commands = generate_multiline_commands("Line 1\nLine 2\nLine 3")
        text_commands = [c[0] for c in commands if c[0] not in ("CTRL+L", "CTRL+J", "ENTER")]
        assert "Line 1" in text_commands
        assert "Line 2" in text_commands
        assert "Line 3" in text_commands

    def test_adds_enter_between_lines(self):
        """Should add ENTER between lines but not after last line."""
        commands = generate_multiline_commands("Line 1\nLine 2")
        enter_count = sum(1 for c in commands if c[0] == "ENTER")
        assert enter_count == 1  # Only one ENTER between two lines

    def test_submits_with_ctrl_j(self):
        """Should submit multiline prompt with CTRL+J."""
        commands = generate_multiline_commands("Line 1\nLine 2")
        assert commands[-1][0] == "CTRL+J"

    def test_default_wait_time(self):
        """Should use default 15s wait time."""
        commands = generate_multiline_commands("Line 1\nLine 2")
        assert commands[-1][1] == 15.0

    def test_custom_wait_time(self):
        """Should use custom wait time when specified."""
        commands = generate_multiline_commands("Complex\nMultiline\nTask", wait=60.0)
        assert commands[-1][1] == 60.0

    def test_strips_outer_whitespace(self):
        """Should strip leading/trailing whitespace from entire text block."""
        commands = generate_multiline_commands("\n  Line 1\n  Line 2  \n\n")
        text_commands = [c[0] for c in commands if c[0] not in ("CTRL+L", "CTRL+J", "ENTER")]
        # Strips outer newlines but preserves individual line content
        assert len(text_commands) == 2
        assert "Line 1" in text_commands[0]
        assert "Line 2" in text_commands[1]

    def test_independent_multiline_mode(self):
        """Each multiline prompt should independently enter multiline mode."""
        # First call
        commands1 = generate_multiline_commands("First prompt")
        assert commands1[0] == ("CTRL+L", 0.3)

        # Second call should also enter multiline mode
        commands2 = generate_multiline_commands("Second prompt")
        assert commands2[0] == ("CTRL+L", 0.3)


class TestGenerateCommandCommands:
    """Test generate_command_commands function."""

    def test_types_slash_command(self):
        """Should type the slash command."""
        commands = generate_command_commands("/history")
        assert commands[0][0] == "/history"

    def test_submits_with_enter(self):
        """Should submit command with ENTER."""
        commands = generate_command_commands("/help")
        assert commands[1][0] == "ENTER"

    def test_short_wait_time(self):
        """Should have short wait time for commands."""
        commands = generate_command_commands("/quit")
        assert commands[1][1] == 1.0


class TestGeneratePaletteCommands:
    """Test generate_palette_commands function."""

    def test_opens_palette_with_ctrl_p(self):
        """Should open palette with CTRL+P."""
        commands = generate_palette_commands()
        assert commands == [("CTRL+P", 0.5)]


class TestGenerateQuitCommands:
    """Test generate_quit_commands function."""

    def test_quits_with_ctrl_q(self):
        """Should quit with CTRL+Q."""
        state = OpenHandsState(running=True)
        commands = generate_quit_commands(state)
        assert commands == [("CTRL+Q", 1.0)]

    def test_updates_state(self):
        """Should update state to not running."""
        state = OpenHandsState(running=True)
        generate_quit_commands(state)
        assert state.running is False


class TestOpenHandsCommandExpander:
    """Test OpenHandsCommandExpander class."""

    def test_is_openhands_command(self):
        """Should correctly identify OpenHands commands."""
        expander = OpenHandsCommandExpander()
        assert expander.is_openhands_command("Install") is True
        assert expander.is_openhands_command("Start") is True
        assert expander.is_openhands_command("Prompt") is True
        assert expander.is_openhands_command("MultilinePrompt") is True
        assert expander.is_openhands_command("Command") is True
        assert expander.is_openhands_command("Palette") is True
        assert expander.is_openhands_command("Quit") is True
        assert expander.is_openhands_command("Type") is False
        assert expander.is_openhands_command("Enter") is False

    def test_expand_install_command(self):
        """Should expand Install command to keystrokes."""
        expander = OpenHandsCommandExpander()
        commands = expander.expand_command("Install", [])
        assert len(commands) > 0
        assert any("uv tool install" in cmd[0] for cmd in commands)

    def test_expand_install_with_version(self):
        """Should expand Install with version argument."""
        expander = OpenHandsCommandExpander()
        commands = expander.expand_command("Install", ["1.14.0"])
        assert any("openhands==1.14.0" in cmd[0] for cmd in commands)

    def test_expand_start_command(self):
        """Should expand Start command to keystrokes."""
        expander = OpenHandsCommandExpander()
        commands = expander.expand_command("Start", [])
        assert len(commands) > 0
        assert any("openhands" in cmd[0] for cmd in commands)

    def test_expand_prompt_command(self):
        """Should expand Prompt command to keystrokes after Start."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])  # Must start first
        commands = expander.expand_command("Prompt", ["Hello world"])
        assert len(commands) > 0
        assert commands[0][0] == "Hello world"
        assert commands[1][0] == "ENTER"

    def test_expand_prompt_empty_args(self):
        """Should return empty list for Prompt with no args."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])  # Must start first
        commands = expander.expand_command("Prompt", [])
        assert commands == []

    def test_expand_prompt_with_wait(self):
        """Should expand Prompt with custom wait time."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])  # Must start first
        commands = expander.expand_command("Prompt", ["Complex task", "30"])
        assert commands[1][1] == 30.0

    def test_expand_multiline_command(self):
        """Should expand MultilinePrompt command to keystrokes after Start."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])  # Must start first
        commands = expander.expand_command("MultilinePrompt", ["Line 1\nLine 2"])
        assert len(commands) > 0
        assert commands[0] == ("CTRL+L", 0.3)
        assert commands[-1][0] == "CTRL+J"

    def test_expand_multiline_empty_args(self):
        """Should return empty list for MultilinePrompt with no args."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])  # Must start first
        commands = expander.expand_command("MultilinePrompt", [])
        assert commands == []

    def test_expand_command_command(self):
        """Should expand Command command to keystrokes after Start."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])  # Must start first
        commands = expander.expand_command("Command", ["/history"])
        assert commands[0][0] == "/history"
        assert commands[1][0] == "ENTER"

    def test_expand_command_empty_args(self):
        """Should return empty list for Command with no args."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])  # Must start first
        commands = expander.expand_command("Command", [])
        assert commands == []

    def test_expand_palette_command(self):
        """Should expand Palette command to keystrokes after Start."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])  # Must start first
        commands = expander.expand_command("Palette", [])
        assert commands == [("CTRL+P", 0.5)]

    def test_expand_quit_command(self):
        """Should expand Quit command to keystrokes after Start."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])  # Must start first
        commands = expander.expand_command("Quit", [])
        assert commands == [("CTRL+Q", 1.0)]

    def test_expand_unknown_command(self):
        """Should return empty list for unknown commands."""
        expander = OpenHandsCommandExpander()
        commands = expander.expand_command("Unknown", ["arg"])
        assert commands == []

    def test_state_persists_across_commands(self):
        """State should persist across command expansions."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])
        assert expander.state.running is True

        expander.expand_command("Quit", [])
        assert expander.state.running is False


class TestOpenHandsStateValidation:
    """Test state validation in OpenHandsCommandExpander."""

    def test_prompt_before_start_raises(self):
        """Prompt before Start should raise ValueError."""
        expander = OpenHandsCommandExpander()
        with pytest.raises(ValueError, match="Cannot use 'Prompt' before 'Start'"):
            expander.expand_command("Prompt", ["Hello"])

    def test_multiline_before_start_raises(self):
        """MultilinePrompt before Start should raise ValueError."""
        expander = OpenHandsCommandExpander()
        with pytest.raises(ValueError, match="Cannot use 'MultilinePrompt' before 'Start'"):
            expander.expand_command("MultilinePrompt", ["Line 1\nLine 2"])

    def test_command_before_start_raises(self):
        """Command before Start should raise ValueError."""
        expander = OpenHandsCommandExpander()
        with pytest.raises(ValueError, match="Cannot use 'Command' before 'Start'"):
            expander.expand_command("Command", ["/history"])

    def test_palette_before_start_raises(self):
        """Palette before Start should raise ValueError."""
        expander = OpenHandsCommandExpander()
        with pytest.raises(ValueError, match="Cannot use 'Palette' before 'Start'"):
            expander.expand_command("Palette", [])

    def test_quit_before_start_raises(self):
        """Quit before Start should raise ValueError."""
        expander = OpenHandsCommandExpander()
        with pytest.raises(ValueError, match="Cannot use 'Quit' before 'Start'"):
            expander.expand_command("Quit", [])

    def test_double_start_raises(self):
        """Start when already running should raise ValueError."""
        expander = OpenHandsCommandExpander()
        expander.expand_command("Start", [])
        with pytest.raises(ValueError, match="Cannot use 'Start' when CLI is already running"):
            expander.expand_command("Start", [])

    def test_install_allowed_anytime(self):
        """Install should work regardless of state."""
        expander = OpenHandsCommandExpander()
        # Before Start
        commands = expander.expand_command("Install", [])
        assert len(commands) > 0

        # After Start
        expander.expand_command("Start", [])
        commands = expander.expand_command("Install", ["1.0.0"])
        assert len(commands) > 0

    def test_full_valid_sequence(self):
        """Full valid sequence: Start -> Prompt -> Command -> Quit."""
        expander = OpenHandsCommandExpander()

        # Start
        commands = expander.expand_command("Start", [])
        assert len(commands) > 0
        assert expander.state.running is True

        # Prompt
        commands = expander.expand_command("Prompt", ["Hello"])
        assert commands[0][0] == "Hello"

        # Command
        commands = expander.expand_command("Command", ["/help"])
        assert commands[0][0] == "/help"

        # Quit
        commands = expander.expand_command("Quit", [])
        assert commands == [("CTRL+Q", 1.0)]
        assert expander.state.running is False

    def test_restart_after_quit(self):
        """Should be able to Start again after Quit."""
        expander = OpenHandsCommandExpander()

        # First session
        expander.expand_command("Start", [])
        expander.expand_command("Quit", [])
        assert expander.state.running is False

        # Second session
        commands = expander.expand_command("Start", [])
        assert len(commands) > 0
        assert expander.state.running is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
