"""Unit tests for preview module.

Tests cover:
- CheckpointResult dataclass
- PreviewResult dataclass
- TerminalPreviewer class methods
- ScriptPreviewer class methods
- Frame capture functionality
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from demorec.preview import (
    CheckpointResult,
    PreviewResult,
    ScriptPreviewer,
    TerminalPreviewer,
)
from demorec.stage import Checkpoint


class TestCheckpointResult:
    """Test CheckpointResult dataclass."""

    def test_checkpoint_result_creation(self):
        """Should create checkpoint result with all fields."""
        cp = Checkpoint(
            line_number=10,
            command_index=5,
            event_type="visual_selection",
            description="Test",
            expected_highlight=(5, 15),
        )
        result = CheckpointResult(
            checkpoint=cp,
            passed=True,
            expected_lines=(5, 15),
            visible_lines=(1, 20),
            screenshot_path=Path("/tmp/test.png"),
            error_message=None,
        )
        assert result.passed is True
        assert result.expected_lines == (5, 15)
        assert result.visible_lines == (1, 20)

    def test_checkpoint_result_failed(self):
        """Should create failed checkpoint result."""
        cp = Checkpoint(10, 5, "visual_selection", "Test")
        result = CheckpointResult(
            checkpoint=cp,
            passed=False,
            expected_lines=(5, 15),
            visible_lines=(1, 10),
            screenshot_path=None,
            error_message="Line 15 not visible",
        )
        assert result.passed is False
        assert result.error_message is not None


class TestPreviewResult:
    """Test PreviewResult dataclass."""

    def test_preview_result_creation(self):
        """Should create preview result with all fields."""
        result = PreviewResult(
            total=5,
            passed=3,
            failed=2,
            results=[],
            screenshot_dir=Path("/tmp/screenshots"),
        )
        assert result.total == 5
        assert result.passed == 3
        assert result.failed == 2

    def test_preview_result_all_passed(self):
        """Should create result with all passed."""
        result = PreviewResult(
            total=3,
            passed=3,
            failed=0,
            results=[],
            screenshot_dir=None,
        )
        assert result.failed == 0


class TestTerminalPreviewerInit:
    """Test TerminalPreviewer initialization."""

    def test_default_init(self):
        """Should initialize with default values."""
        previewer = TerminalPreviewer()
        assert previewer.rows == 30
        assert previewer.width == 1280
        assert previewer.height == 720
        assert previewer.screenshots == "on_error"

    def test_custom_init(self):
        """Should accept custom values."""
        previewer = TerminalPreviewer(
            rows=40,
            width=1920,
            height=1080,
            screenshots="always",
        )
        assert previewer.rows == 40
        assert previewer.width == 1920
        assert previewer.screenshots == "always"


class TestTerminalPreviewerHelpers:
    """Test TerminalPreviewer helper methods."""

    def test_setup_screenshot_dir_never(self):
        """Should return None when screenshots='never'."""
        from demorec.frame_capture import setup_screenshot_dir

        previewer = TerminalPreviewer(screenshots="never")
        result = setup_screenshot_dir(previewer._state, None)
        assert result is None

    def test_setup_screenshot_dir_with_output(self):
        """Should use provided output directory."""
        from demorec.frame_capture import setup_screenshot_dir

        previewer = TerminalPreviewer(screenshots="on_error")
        with patch.object(Path, "mkdir"):
            result = setup_screenshot_dir(previewer._state, Path("/custom/dir"))
            assert result == Path("/custom/dir")

    def test_build_checkpoint_result(self):
        """Should build CheckpointResult from checkpoint data."""
        previewer = TerminalPreviewer()
        cp = Checkpoint(10, 5, "test", "desc", expected_highlight=(5, 15))
        # _build_result builds a CheckpointResult from individual pieces
        result = previewer._build_result(
            cp=cp,
            passed=True,
            visible=(1, 20),
            screenshot=Path("/tmp/test.png"),
            error=None,
        )
        assert result.passed is True
        assert result.checkpoint == cp
        assert result.expected_lines == (5, 15)
        assert result.visible_lines == (1, 20)
        assert result.screenshot_path == Path("/tmp/test.png")
        assert result.error_message is None

    def test_extract_line_range_with_line_numbers(self):
        """Should extract line range from vim-formatted lines."""
        previewer = TerminalPreviewer()
        visible_lines = [
            "  1 def hello():",
            "  2     print('hello')",
            "  3 ",
            " 10 def world():",
        ]
        result = previewer._extract_line_range(visible_lines)
        assert result == (1, 10)

    def test_extract_line_range_no_numbers(self):
        """Should return None if no line numbers found."""
        previewer = TerminalPreviewer()
        visible_lines = [
            "hello world",
            "no line numbers here",
        ]
        result = previewer._extract_line_range(visible_lines)
        assert result is None

    def test_extract_line_range_empty(self):
        """Should return None for empty list."""
        previewer = TerminalPreviewer()
        result = previewer._extract_line_range([])
        assert result is None

    def test_check_visibility_both_none(self):
        """Should pass when no expected or visible lines."""
        previewer = TerminalPreviewer()
        passed, error = previewer._check_visibility(None, None)
        assert passed is True
        assert error is None

    def test_check_visibility_visible_range(self):
        """Should pass when expected is within visible range."""
        previewer = TerminalPreviewer()
        passed, error = previewer._check_visibility((5, 10), (1, 20))
        assert passed is True
        assert error is None

    def test_check_visibility_start_not_visible(self):
        """Should fail when expected start not visible."""
        previewer = TerminalPreviewer()
        passed, error = previewer._check_visibility((5, 15), (10, 20))
        assert passed is False
        assert "Line 5 not visible" in error

    def test_check_visibility_end_not_visible(self):
        """Should fail when expected end not visible."""
        previewer = TerminalPreviewer()
        passed, error = previewer._check_visibility((5, 25), (1, 20))
        assert passed is False
        assert "Line 25 not visible" in error

    def test_parse_duration_seconds(self):
        """Should parse seconds duration."""
        from demorec.frame_capture import parse_duration

        assert parse_duration("1s") == 1.0
        assert parse_duration("0.5s") == 0.5
        assert parse_duration("2.5s") == 2.5

    def test_parse_duration_milliseconds(self):
        """Should parse milliseconds duration."""
        from demorec.frame_capture import parse_duration

        assert parse_duration("500ms") == 0.5
        assert parse_duration("1000ms") == 1.0

    def test_parse_duration_plain_number(self):
        """Should parse plain number as seconds."""
        from demorec.frame_capture import parse_duration

        assert parse_duration("2") == 2.0


class TestTerminalPreviewerTypeCommands:
    """Test TerminalPreviewer type command processing."""

    def test_process_type_cmd_goto(self):
        """Should track goto command."""
        previewer = TerminalPreviewer()
        state = {"in_visual": False, "visual_start": None, "goto": None, "goto_idx": 0}
        previewer._process_type_cmd("15G", 5, state)
        assert state["goto"] == 15
        assert state["goto_idx"] == 5

    def test_process_type_cmd_visual_v(self):
        """Should enter visual mode on V."""
        previewer = TerminalPreviewer()
        state = {"in_visual": False, "visual_start": None, "goto": 10, "goto_idx": 0}
        previewer._process_type_cmd("V", 5, state)
        assert state["in_visual"] is True
        assert state["visual_start"] == 10

    def test_process_type_cmd_visual_lowercase_v(self):
        """Should enter visual mode on lowercase v."""
        previewer = TerminalPreviewer()
        state = {"in_visual": False, "visual_start": None, "goto": 10, "goto_idx": 0}
        previewer._process_type_cmd("v", 5, state)
        assert state["in_visual"] is True

    def test_process_escape_creates_checkpoint(self):
        """Should create checkpoint on escape from visual mode."""
        previewer = TerminalPreviewer()
        state = {"in_visual": True, "visual_start": 10, "goto": 20, "goto_idx": 5}
        checkpoint = previewer._process_escape(state)
        assert checkpoint is not None
        assert checkpoint.expected_highlight == (10, 20)

    def test_process_escape_clears_state(self):
        """Should clear visual state on escape."""
        previewer = TerminalPreviewer()
        state = {"in_visual": True, "visual_start": 10, "goto": 20, "goto_idx": 5}
        previewer._process_escape(state)
        assert state["in_visual"] is False
        assert state["visual_start"] is None

    def test_process_escape_no_visual_mode(self):
        """Should return None if not in visual mode."""
        previewer = TerminalPreviewer()
        state = {"in_visual": False, "visual_start": None, "goto": None, "goto_idx": 0}
        checkpoint = previewer._process_escape(state)
        assert checkpoint is None

    def test_create_visual_checkpoint_orders_lines(self):
        """Should order lines correctly (min, max)."""
        previewer = TerminalPreviewer()
        state = {"in_visual": True, "visual_start": 20, "goto": 10, "goto_idx": 5}
        checkpoint = previewer._create_visual_checkpoint(state)
        assert checkpoint.expected_highlight == (10, 20)


class TestTerminalPreviewerCheckpointDetection:
    """Test checkpoint detection from commands."""

    def test_detect_checkpoints_from_commands(self):
        """Should detect checkpoints from command list."""
        from demorec.parser import Command

        previewer = TerminalPreviewer()
        commands = [
            Command("Type", ["vim file.py"]),
            Command("Enter", []),
            Command("Type", ["10G"]),
            Command("Type", ["V"]),
            Command("Type", ["20G"]),
            Command("Escape", []),
        ]

        # Create mock segment
        class MockSegment:
            pass

        segment = MockSegment()
        segment.commands = commands

        checkpoints = previewer._detect_checkpoints_from_commands(commands)
        assert len(checkpoints) == 1
        assert checkpoints[0].expected_highlight == (10, 20)

    def test_detect_no_checkpoints(self):
        """Should return empty list when no visual selections."""
        from demorec.parser import Command

        previewer = TerminalPreviewer()
        commands = [
            Command("Type", ["hello"]),
            Command("Enter", []),
        ]
        checkpoints = previewer._detect_checkpoints_from_commands(commands)
        assert checkpoints == []


class TestTerminalPreviewerScreenshots:
    """Test screenshot logic."""

    @pytest.mark.asyncio
    async def test_maybe_screenshot_never(self):
        """Should not screenshot when mode is 'never'."""
        previewer = TerminalPreviewer(screenshots="never")
        result = await previewer._maybe_screenshot(MagicMock(), Path("/tmp"), 1, "test", False)
        assert result is None

    @pytest.mark.asyncio
    async def test_maybe_screenshot_on_error_passed(self):
        """Should not screenshot on_error when passed."""
        previewer = TerminalPreviewer(screenshots="on_error")
        result = await previewer._maybe_screenshot(MagicMock(), Path("/tmp"), 1, "test", True)
        assert result is None

    @pytest.mark.asyncio
    async def test_maybe_screenshot_on_error_failed(self):
        """Should screenshot on_error when failed."""
        previewer = TerminalPreviewer(screenshots="on_error")
        mock_page = AsyncMock()
        result = await previewer._maybe_screenshot(mock_page, Path("/tmp"), 1, "test", False)
        assert result == Path("/tmp/checkpoint_1_test.png")
        mock_page.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_screenshot_always(self):
        """Should screenshot when mode is 'always'."""
        previewer = TerminalPreviewer(screenshots="always")
        mock_page = AsyncMock()
        result = await previewer._maybe_screenshot(mock_page, Path("/tmp"), 1, "test", True)
        assert result is not None
        mock_page.screenshot.assert_called_once()


class TestTerminalPreviewerDispatch:
    """Test command dispatch."""

    @pytest.mark.asyncio
    async def test_dispatch_type_command(self):
        """Should handle Type command."""
        from demorec.parser import Command

        previewer = TerminalPreviewer()
        mock_page = AsyncMock()
        cmd = Command("Type", ["hello"])
        await previewer._dispatch_command(mock_page, cmd)
        # Type calls keyboard.type for each character
        assert mock_page.keyboard.type.called

    @pytest.mark.asyncio
    async def test_dispatch_enter_command(self):
        """Should handle Enter command."""
        from demorec.parser import Command

        previewer = TerminalPreviewer()
        mock_page = AsyncMock()
        cmd = Command("Enter", [])
        await previewer._dispatch_command(mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Enter")

    @pytest.mark.asyncio
    async def test_dispatch_escape_command(self):
        """Should handle Escape command."""
        from demorec.parser import Command

        previewer = TerminalPreviewer()
        mock_page = AsyncMock()
        cmd = Command("Escape", [])
        await previewer._dispatch_command(mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Escape")

    @pytest.mark.asyncio
    async def test_dispatch_clear_command(self):
        """Should handle Clear command."""
        from demorec.parser import Command

        previewer = TerminalPreviewer()
        mock_page = AsyncMock()
        cmd = Command("Clear", [])
        await previewer._dispatch_command(mock_page, cmd)
        mock_page.keyboard.press.assert_called_with("Control+l")

    @pytest.mark.asyncio
    async def test_dispatch_sleep_command(self):
        """Should handle Sleep command."""
        from demorec.parser import Command

        previewer = TerminalPreviewer()
        mock_page = AsyncMock()
        cmd = Command("Sleep", ["0.01s"])

        # Should not raise and should complete quickly
        await previewer._dispatch_command(mock_page, cmd)


class TestPreviewResultWithFrames:
    """Test PreviewResult with frame capture fields."""

    def test_preview_result_with_frames(self):
        """Should include frame count and frames directory."""
        result = PreviewResult(
            total=3,
            passed=3,
            failed=0,
            results=[],
            screenshot_dir=None,
            frame_count=25,
            frames_dir=Path("/tmp/frames"),
        )
        assert result.frame_count == 25
        assert result.frames_dir == Path("/tmp/frames")

    def test_preview_result_defaults_no_frames(self):
        """Should default to no frames."""
        result = PreviewResult(
            total=1,
            passed=1,
            failed=0,
            results=[],
            screenshot_dir=None,
        )
        assert result.frame_count == 0
        assert result.frames_dir is None


class TestTerminalPreviewerFrameCapture:
    """Test TerminalPreviewer frame capture functionality."""

    def test_init_with_capture_frames(self):
        """Should initialize with capture_frames flag."""
        previewer = TerminalPreviewer(capture_frames=True)
        assert previewer.capture_frames is True
        assert previewer._state.frame_counter == 0
        assert previewer._state.start_time is None

    def test_init_without_capture_frames(self):
        """Should default capture_frames to False."""
        previewer = TerminalPreviewer()
        assert previewer.capture_frames is False

    def test_setup_frames_dir_disabled(self):
        """Should not set up frames dir when capture disabled."""
        from demorec.frame_capture import setup_frames_dir

        previewer = TerminalPreviewer(capture_frames=False)
        setup_frames_dir(previewer._state, Path("/tmp/frames"))
        assert previewer._state.frames_dir is None

    def test_setup_frames_dir_no_output(self):
        """Should not set up frames dir when no output dir provided."""
        from demorec.frame_capture import setup_frames_dir

        previewer = TerminalPreviewer(capture_frames=True)
        setup_frames_dir(previewer._state, None)
        assert previewer._state.frames_dir is None

    def test_setup_frames_dir_enabled(self):
        """Should set up frames dir when enabled with output dir."""
        from demorec.frame_capture import setup_frames_dir

        previewer = TerminalPreviewer(capture_frames=True)
        with patch.object(Path, "mkdir"):
            setup_frames_dir(previewer._state, Path("/tmp/frames"))
        assert previewer._state.frames_dir == Path("/tmp/frames")
        assert previewer._state.frame_counter == 0

    @pytest.mark.asyncio
    async def test_capture_frame_disabled(self):
        """Should return None when frame capture is disabled."""
        from demorec.frame_capture import capture_frame

        previewer = TerminalPreviewer(capture_frames=False)
        result = await capture_frame(previewer._state, MagicMock(), "terminal")
        assert result is None

    @pytest.mark.asyncio
    async def test_capture_frame_no_start_time(self):
        """Should return None when start time not set."""
        from demorec.frame_capture import capture_frame

        previewer = TerminalPreviewer(capture_frames=True)
        previewer._state.frames_dir = Path("/tmp/frames")
        previewer._state.start_time = None
        result = await capture_frame(previewer._state, MagicMock(), "terminal")
        assert result is None


class TestScriptPreviewerInit:
    """Test ScriptPreviewer initialization."""

    def test_default_init(self):
        """Should initialize with default values."""
        previewer = ScriptPreviewer()
        assert previewer.rows == 30
        assert previewer.width == 1280
        assert previewer.height == 720
        assert previewer.screenshots == "on_error"
        assert previewer.capture_frames is False

    def test_custom_init(self):
        """Should accept custom values."""
        previewer = ScriptPreviewer(
            rows=40,
            width=1920,
            height=1080,
            screenshots="always",
            capture_frames=True,
        )
        assert previewer.rows == 40
        assert previewer.width == 1920
        assert previewer.height == 1080
        assert previewer.screenshots == "always"
        assert previewer.capture_frames is True


class TestScriptPreviewerHelpers:
    """Test ScriptPreviewer helper methods."""

    def test_setup_frames_dir_enabled(self):
        """Should set up frames directory when enabled."""
        from demorec.frame_capture import setup_frames_dir

        previewer = ScriptPreviewer(capture_frames=True)
        with patch.object(Path, "mkdir"):
            setup_frames_dir(previewer._state, Path("/tmp/frames"))
        assert previewer._state.frames_dir == Path("/tmp/frames")
        assert previewer._state.frame_counter == 0

    def test_setup_frames_dir_disabled(self):
        """Should not set up frames directory when disabled."""
        from demorec.frame_capture import setup_frames_dir

        previewer = ScriptPreviewer(capture_frames=False)
        setup_frames_dir(previewer._state, Path("/tmp/frames"))
        assert previewer._state.frames_dir is None

    def test_setup_screenshot_dir_never(self):
        """Should return None when screenshots='never'."""
        from demorec.frame_capture import setup_screenshot_dir

        previewer = ScriptPreviewer(screenshots="never")
        result = setup_screenshot_dir(previewer._state, None)
        assert result is None

    def test_setup_screenshot_dir_with_output(self):
        """Should use provided output directory."""
        from demorec.frame_capture import setup_screenshot_dir

        previewer = ScriptPreviewer(screenshots="on_error")
        with patch.object(Path, "mkdir"):
            result = setup_screenshot_dir(previewer._state, Path("/custom/dir"))
        assert result == Path("/custom/dir")

    def test_build_preview_result_with_frames(self):
        """Should include frame info in result."""
        from demorec.preview import build_preview_result

        previewer = ScriptPreviewer(capture_frames=True)
        previewer._state.frame_counter = 15
        previewer._state.frames_dir = Path("/tmp/frames")

        result = build_preview_result([], None, previewer._state)

        assert result.frame_count == 15
        assert result.frames_dir == Path("/tmp/frames")

    def test_parse_duration_seconds(self):
        """Should parse seconds duration."""
        from demorec.frame_capture import parse_duration

        assert parse_duration("1s") == 1.0
        assert parse_duration("0.5s") == 0.5
        assert parse_duration("2.5s") == 2.5

    def test_parse_duration_milliseconds(self):
        """Should parse milliseconds duration."""
        from demorec.frame_capture import parse_duration

        assert parse_duration("500ms") == 0.5
        assert parse_duration("1000ms") == 1.0

    def test_parse_duration_plain_number(self):
        """Should parse plain number as seconds."""
        from demorec.frame_capture import parse_duration

        assert parse_duration("2") == 2.0


class TestScriptPreviewerFrameCapture:
    """Test ScriptPreviewer frame capture functionality."""

    @pytest.mark.asyncio
    async def test_capture_frame_disabled(self):
        """Should return None when frame capture is disabled."""
        from demorec.frame_capture import capture_frame

        previewer = ScriptPreviewer(capture_frames=False)
        result = await capture_frame(previewer._state, MagicMock(), "terminal")
        assert result is None

    @pytest.mark.asyncio
    async def test_capture_frame_no_start_time(self):
        """Should return None when start time not set."""
        from demorec.frame_capture import capture_frame

        previewer = ScriptPreviewer(capture_frames=True)
        previewer._state.frames_dir = Path("/tmp/frames")
        previewer._state.start_time = None
        result = await capture_frame(previewer._state, MagicMock(), "terminal")
        assert result is None

    @pytest.mark.asyncio
    async def test_capture_frame_increments_counter(self):
        """Should increment frame counter on capture."""
        import tempfile
        import time

        from demorec.frame_capture import capture_frame

        previewer = ScriptPreviewer(capture_frames=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            previewer._state.frames_dir = Path(tmpdir)
            previewer._state.start_time = time.time()
            previewer._state.frame_counter = 0

            # Mock page for browser screenshot
            mock_page = AsyncMock()

            await capture_frame(previewer._state, mock_page, "browser")
            assert previewer._state.frame_counter == 1

            await capture_frame(previewer._state, mock_page, "browser")
            assert previewer._state.frame_counter == 2

    @pytest.mark.asyncio
    async def test_capture_browser_frame_creates_png(self):
        """Should create PNG file for browser frame."""
        import tempfile
        import time

        from demorec.frame_capture import capture_frame

        previewer = ScriptPreviewer(capture_frames=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            previewer._state.frames_dir = Path(tmpdir)
            previewer._state.start_time = time.time()
            previewer._state.frame_counter = 0

            mock_page = AsyncMock()

            result = await capture_frame(previewer._state, mock_page, "browser")

            assert result is not None
            assert result.suffix == ".png"
            assert "frame_0001_" in result.name
            mock_page.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_capture_terminal_frame_creates_txt(self):
        """Should create TXT file for terminal frame."""
        import tempfile
        import time

        from demorec.frame_capture import capture_frame

        previewer = ScriptPreviewer(capture_frames=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            previewer._state.frames_dir = Path(tmpdir)
            previewer._state.start_time = time.time()
            previewer._state.frame_counter = 0

            mock_page = AsyncMock()

            # Mock get_buffer_state
            from demorec.xterm import BufferState

            mock_buffer = BufferState(
                rows=30,
                cols=80,
                viewport_y=0,
                visible_lines=["line 1", "line 2", "line 3"],
            )

            with patch("demorec.frame_capture.get_buffer_state", return_value=mock_buffer):
                result = await capture_frame(previewer._state, mock_page, "terminal")

            assert result is not None
            assert result.suffix == ".txt"
            assert "frame_0001_" in result.name
            assert result.exists()

            content = result.read_text()
            assert "line 1" in content
            assert "line 2" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
