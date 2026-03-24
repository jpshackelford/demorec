"""Unit tests for checkpoints module.

Tests cover:
- Checkpoint dataclass
- _parse_type_command
- _parse_goto
- _is_visual_mode_start
- _should_skip_line
- detect_checkpoints
- _process_lines
- _CheckpointDetectorState
- format_checkpoints_text
- format_checkpoints_json
"""

import json
import tempfile
from pathlib import Path

import pytest

from demorec.checkpoints import (
    Checkpoint,
    _CheckpointDetectorState,
    _create_selection_checkpoint,
    _handle_comment,
    _handle_escape,
    _handle_type_command,
    _is_visual_mode_start,
    _parse_goto,
    _parse_type_command,
    _process_command_line,
    _process_line,
    _process_lines,
    _should_skip_line,
    detect_checkpoints,
    format_checkpoints_json,
    format_checkpoints_text,
)


class TestCheckpointDataclass:
    """Test Checkpoint dataclass."""

    def test_checkpoint_creation_basic(self):
        """Should create checkpoint with required fields."""
        cp = Checkpoint(
            line_number=10,
            command_index=5,
            event_type="visual_selection",
            description="Test checkpoint",
        )
        assert cp.line_number == 10
        assert cp.command_index == 5
        assert cp.event_type == "visual_selection"
        assert cp.description == "Test checkpoint"
        assert cp.expected_highlight is None

    def test_checkpoint_with_highlight(self):
        """Should create checkpoint with expected_highlight."""
        cp = Checkpoint(
            line_number=10,
            command_index=5,
            event_type="visual_selection",
            description="Test",
            expected_highlight=(5, 15),
        )
        assert cp.expected_highlight == (5, 15)


class TestParseTypeCommand:
    """Test _parse_type_command function."""

    def test_parse_valid_type_command(self):
        """Should parse valid Type command."""
        result = _parse_type_command('Type "hello"')
        assert result == "hello"

    def test_parse_type_with_vim_commands(self):
        """Should parse Type commands with vim content."""
        assert _parse_type_command('Type "10G"') == "10G"
        assert _parse_type_command('Type "V"') == "V"
        assert _parse_type_command('Type ":wq"') == ":wq"

    def test_parse_invalid_line(self):
        """Should return None for non-Type lines."""
        assert _parse_type_command("Enter") is None
        assert _parse_type_command("Sleep 1s") is None
        assert _parse_type_command("Escape") is None

    def test_parse_empty_type(self):
        """Should handle Type with empty string - returns None for empty match."""
        result = _parse_type_command('Type ""')
        # Empty content between quotes doesn't match the regex pattern [^"]+
        assert result is None


class TestParseGoto:
    """Test _parse_goto function."""

    def test_parse_valid_goto(self):
        """Should parse valid goto commands."""
        assert _parse_goto("10G") == 10
        assert _parse_goto("1G") == 1
        assert _parse_goto("999G") == 999

    def test_parse_invalid_goto(self):
        """Should return None for invalid goto."""
        assert _parse_goto("V") is None
        assert _parse_goto("hello") is None
        assert _parse_goto("G10") is None
        assert _parse_goto("") is None


class TestIsVisualModeStart:
    """Test _is_visual_mode_start function."""

    def test_visual_mode_v(self):
        """Should detect 'V' as visual mode start."""
        assert _is_visual_mode_start("V") is True

    def test_visual_mode_lowercase_v(self):
        """Should detect 'v' as visual mode start."""
        assert _is_visual_mode_start("v") is True

    def test_non_visual_content(self):
        """Should return False for non-visual content."""
        assert _is_visual_mode_start("10G") is False
        assert _is_visual_mode_start(":wq") is False
        assert _is_visual_mode_start("VV") is False


class TestShouldSkipLine:
    """Test _should_skip_line function."""

    def test_skip_empty_line(self):
        """Should skip empty lines."""
        assert _should_skip_line("") is True

    def test_skip_directive_lines(self):
        """Should skip lines starting with @."""
        assert _should_skip_line("@mode terminal") is True
        assert _should_skip_line("@terminal:rows 30") is True

    def test_skip_set_directive(self):
        """Should skip Set directives."""
        assert _should_skip_line("Set Width 1280") is True
        assert _should_skip_line("Set Height 720") is True

    def test_skip_output_directive(self):
        """Should skip Output directive."""
        assert _should_skip_line("Output test.mp4") is True

    def test_dont_skip_commands(self):
        """Should not skip regular commands."""
        assert _should_skip_line('Type "hello"') is False
        assert _should_skip_line("Enter") is False
        assert _should_skip_line("Escape") is False


class TestCheckpointDetectorState:
    """Test _CheckpointDetectorState class."""

    def test_initial_state(self):
        """Should initialize with correct default values."""
        state = _CheckpointDetectorState()
        assert state.command_index == 0
        assert state.in_visual_mode is False
        assert state.visual_start_line is None
        assert state.pending_goto is None
        assert state.last_type_line == 0


class TestHandleTypeCommand:
    """Test _handle_type_command function."""

    def test_updates_last_type_line(self):
        """Should update last_type_line."""
        state = _CheckpointDetectorState()
        _handle_type_command("hello", 10, state)
        assert state.last_type_line == 10

    def test_increments_command_index(self):
        """Should increment command_index."""
        state = _CheckpointDetectorState()
        _handle_type_command("hello", 10, state)
        assert state.command_index == 1

    def test_sets_pending_goto(self):
        """Should set pending_goto for goto commands."""
        state = _CheckpointDetectorState()
        _handle_type_command("15G", 10, state)
        assert state.pending_goto == 15

    def test_sets_visual_mode(self):
        """Should set visual mode for V."""
        state = _CheckpointDetectorState()
        state.pending_goto = 10  # Set goto first
        _handle_type_command("V", 15, state)
        assert state.in_visual_mode is True
        assert state.visual_start_line == 10


class TestHandleComment:
    """Test _handle_comment function."""

    def test_handles_narrate_after(self):
        """Should create checkpoint for @narrate:after."""
        state = _CheckpointDetectorState()
        state.command_index = 5
        checkpoints = []
        _handle_comment('# @narrate:after "Some text"', 10, state, checkpoints)
        assert len(checkpoints) == 1
        assert checkpoints[0].event_type == "narration"
        assert checkpoints[0].line_number == 10

    def test_ignores_regular_comments(self):
        """Should not create checkpoints for regular comments."""
        state = _CheckpointDetectorState()
        checkpoints = []
        _handle_comment("# This is a regular comment", 10, state, checkpoints)
        assert len(checkpoints) == 0


class TestHandleEscape:
    """Test _handle_escape function."""

    def test_creates_checkpoint_on_visual_mode_escape(self):
        """Should create checkpoint when escaping visual mode."""
        state = _CheckpointDetectorState()
        state.in_visual_mode = True
        state.visual_start_line = 10
        state.pending_goto = 20
        state.last_type_line = 15
        state.command_index = 5
        checkpoints = []

        _handle_escape(20, state, checkpoints)

        assert len(checkpoints) == 1
        assert checkpoints[0].event_type == "visual_selection"
        assert checkpoints[0].expected_highlight == (10, 20)
        assert state.in_visual_mode is False

    def test_no_checkpoint_without_visual_mode(self):
        """Should not create checkpoint if not in visual mode."""
        state = _CheckpointDetectorState()
        checkpoints = []

        _handle_escape(10, state, checkpoints)

        assert len(checkpoints) == 0


class TestCreateSelectionCheckpoint:
    """Test _create_selection_checkpoint function."""

    def test_creates_checkpoint_with_correct_range(self):
        """Should create checkpoint with min/max ordered lines."""
        state = _CheckpointDetectorState()
        state.visual_start_line = 20
        state.pending_goto = 10
        state.last_type_line = 15
        state.command_index = 5

        cp = _create_selection_checkpoint(state)

        assert cp.expected_highlight == (10, 20)  # min, max
        assert cp.event_type == "visual_selection"


class TestProcessLine:
    """Test _process_line function."""

    def test_handles_comment_line(self):
        """Should delegate comment lines to _handle_comment."""
        state = _CheckpointDetectorState()
        checkpoints = []

        _process_line("# comment", 1, state, checkpoints)
        # Should not raise, comment handling is delegated

    def test_handles_command_line(self):
        """Should process command lines."""
        state = _CheckpointDetectorState()
        checkpoints = []

        _process_line('Type "10G"', 1, state, checkpoints)
        assert state.command_index == 1
        assert state.pending_goto == 10


class TestProcessLines:
    """Test _process_lines function."""

    def test_processes_multiple_lines(self):
        """Should process all lines."""
        lines = [
            'Type "10G"',
            'Type "V"',
            'Type "20G"',
            "Escape",
        ]
        checkpoints = _process_lines(lines)

        assert len(checkpoints) == 1
        assert checkpoints[0].event_type == "visual_selection"


class TestDetectCheckpoints:
    """Test detect_checkpoints function."""

    def test_detect_checkpoints_from_file(self):
        """Should detect checkpoints from a script file."""
        script_content = '''
@mode terminal
Type "vim file.py"
Enter
Type "10G"
Type "V"
Type "20G"
Escape
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script_content)
            script_path = Path(f.name)

        try:
            checkpoints = detect_checkpoints(script_path)
            assert len(checkpoints) == 1
            assert checkpoints[0].event_type == "visual_selection"
        finally:
            script_path.unlink()

    def test_detect_checkpoints_empty_file(self):
        """Should return empty list for file without checkpoints."""
        script_content = '''
@mode terminal
Type "hello"
Enter
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script_content)
            script_path = Path(f.name)

        try:
            checkpoints = detect_checkpoints(script_path)
            assert checkpoints == []
        finally:
            script_path.unlink()


class TestFormatCheckpointsText:
    """Test format_checkpoints_text function."""

    def test_format_empty_checkpoints(self):
        """Should return message for empty list."""
        result = format_checkpoints_text([])
        assert result == "No checkpoints detected."

    def test_format_single_checkpoint(self):
        """Should format single checkpoint correctly."""
        cp = Checkpoint(
            line_number=10,
            command_index=5,
            event_type="visual_selection",
            description="Test checkpoint",
            expected_highlight=(5, 15),
        )
        result = format_checkpoints_text([cp])

        assert "Detected 1 checkpoints" in result
        assert "Checkpoint 1 (line 10)" in result
        assert "Event: visual_selection" in result
        assert "Description: Test checkpoint" in result
        assert "Expected visible: lines 5-15" in result

    def test_format_multiple_checkpoints(self):
        """Should format multiple checkpoints."""
        checkpoints = [
            Checkpoint(1, 0, "visual_selection", "First"),
            Checkpoint(5, 2, "narration", "Second"),
        ]
        result = format_checkpoints_text(checkpoints)

        assert "Detected 2 checkpoints" in result
        assert "Checkpoint 1" in result
        assert "Checkpoint 2" in result


class TestFormatCheckpointsJson:
    """Test format_checkpoints_json function."""

    def test_format_json_structure(self):
        """Should return valid JSON with correct structure."""
        cp = Checkpoint(
            line_number=10,
            command_index=5,
            event_type="visual_selection",
            description="Test",
            expected_highlight=(5, 15),
        )
        result = format_checkpoints_json([cp])
        data = json.loads(result)

        assert data["checkpoint_count"] == 1
        assert len(data["checkpoints"]) == 1
        assert data["checkpoints"][0]["line_number"] == 10
        assert data["checkpoints"][0]["expected_highlight"] == [5, 15]

    def test_format_json_empty(self):
        """Should handle empty checkpoint list."""
        result = format_checkpoints_json([])
        data = json.loads(result)

        assert data["checkpoint_count"] == 0
        assert data["checkpoints"] == []

    def test_format_json_null_highlight(self):
        """Should handle checkpoint without highlight."""
        cp = Checkpoint(10, 5, "narration", "Test")
        result = format_checkpoints_json([cp])
        data = json.loads(result)

        assert data["checkpoints"][0]["expected_highlight"] is None


class TestProcessCommandLine:
    """Test _process_command_line function."""

    def test_handles_type_command(self):
        """Should process Type commands."""
        state = _CheckpointDetectorState()
        checkpoints = []

        _process_command_line('Type "hello"', 1, state, checkpoints)
        assert state.command_index == 1

    def test_handles_escape(self):
        """Should process Escape command."""
        state = _CheckpointDetectorState()
        state.in_visual_mode = True
        state.visual_start_line = 5
        state.pending_goto = 10
        checkpoints = []

        _process_command_line("Escape", 1, state, checkpoints)
        assert state.in_visual_mode is False

    def test_handles_enter(self):
        """Should process Enter command."""
        state = _CheckpointDetectorState()
        checkpoints = []

        _process_command_line("Enter", 1, state, checkpoints)
        assert state.command_index == 1

    def test_handles_sleep(self):
        """Should process Sleep command."""
        state = _CheckpointDetectorState()
        checkpoints = []

        _process_command_line("Sleep 1s", 1, state, checkpoints)
        assert state.command_index == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
