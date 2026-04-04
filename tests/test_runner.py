"""Unit tests for runner module.

Tests cover:
- TimedNarration dataclass
- Runner class initialization
- Runner helper methods
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from demorec.parser import Command, Plan, Segment
from demorec.runner import Runner, TimedNarration


class TestTimedNarration:
    """Test TimedNarration dataclass."""

    def test_timed_narration_creation(self):
        """Should create timed narration with all fields."""
        tn = TimedNarration(
            text="Hello world",
            mode="before",
            audio_path=Path("/tmp/test.mp3"),
            duration=2.5,
            start_time=1.0,
            cmd_index=3,
        )
        assert tn.text == "Hello world"
        assert tn.mode == "before"
        assert tn.audio_path == Path("/tmp/test.mp3")
        assert tn.duration == 2.5
        assert tn.start_time == 1.0
        assert tn.cmd_index == 3

    def test_timed_narration_defaults(self):
        """Should have default start_time and cmd_index."""
        tn = TimedNarration(
            text="Test",
            mode="after",
            audio_path=Path("/tmp/test.mp3"),
            duration=1.0,
        )
        assert tn.start_time == 0.0
        assert tn.cmd_index == 0


class TestRunnerInit:
    """Test Runner initialization."""

    def test_runner_creates_temp_dir(self):
        """Should create temporary directory."""
        plan = Plan()
        runner = Runner(plan)
        assert runner.temp_dir.exists()
        runner.cleanup()

    def test_runner_stores_plan(self):
        """Should store plan reference."""
        plan = Plan(output=Path("test.mp4"))
        runner = Runner(plan)
        assert runner.plan == plan
        assert runner.plan.output == Path("test.mp4")
        runner.cleanup()

    def test_runner_detects_narration(self):
        """Should detect if plan has narration."""
        from demorec.parser import Narration

        plan = Plan(segments=[Segment(mode="terminal", narrations={0: MagicMock()})])
        runner = Runner(plan)
        assert runner.has_narration is True
        runner.cleanup()

    def test_runner_no_narration(self):
        """Should detect if plan has no narration."""
        plan = Plan(segments=[Segment(mode="terminal")])
        runner = Runner(plan)
        assert runner.has_narration is False
        runner.cleanup()

    def test_runner_cleanup(self):
        """Should remove temp directory on cleanup."""
        plan = Plan()
        runner = Runner(plan)
        temp_dir = runner.temp_dir
        assert temp_dir.exists()
        runner.cleanup()
        assert not temp_dir.exists()


class TestRunnerVimPrimitives:
    """Test _uses_vim_submode method."""

    def test_detects_open_command(self):
        """Should detect Open as vim primitive."""
        plan = Plan(
            segments=[
                Segment(mode="terminal", commands=[Command("Open", ["file.py"])])
            ]
        )
        runner = Runner(plan)
        assert runner._uses_vim_submode() is True
        runner.cleanup()

    def test_detects_highlight_command(self):
        """Should detect Highlight as vim primitive."""
        plan = Plan(
            segments=[
                Segment(mode="terminal", commands=[Command("Highlight", ["10-20"])])
            ]
        )
        runner = Runner(plan)
        assert runner._uses_vim_submode() is True
        runner.cleanup()

    def test_detects_close_command(self):
        """Should detect Close as vim primitive."""
        plan = Plan(
            segments=[Segment(mode="terminal", commands=[Command("Close", [])])]
        )
        runner = Runner(plan)
        assert runner._uses_vim_submode() is True
        runner.cleanup()

    def test_detects_goto_command(self):
        """Should detect Goto as vim primitive."""
        plan = Plan(
            segments=[Segment(mode="terminal", commands=[Command("Goto", ["50"])])]
        )
        runner = Runner(plan)
        assert runner._uses_vim_submode() is True
        runner.cleanup()

    def test_no_vim_primitives(self):
        """Should return False when no vim primitives."""
        plan = Plan(
            segments=[
                Segment(
                    mode="terminal",
                    commands=[Command("Type", ["hello"]), Command("Enter", [])],
                )
            ]
        )
        runner = Runner(plan)
        assert runner._uses_vim_submode() is False
        runner.cleanup()

    def test_multiple_segments(self):
        """Should check all segments for vim primitives."""
        plan = Plan(
            segments=[
                Segment(mode="terminal", commands=[Command("Type", ["hello"])]),
                Segment(mode="terminal", commands=[Command("Open", ["file.py"])]),
            ]
        )
        runner = Runner(plan)
        assert runner._uses_vim_submode() is True
        runner.cleanup()


class TestRunnerCreateRecorder:
    """Test _create_recorder method."""

    def test_creates_terminal_recorder(self):
        """Should create TerminalRecorder for terminal mode."""
        plan = Plan()
        runner = Runner(plan)
        segment = Segment(mode="terminal")
        recorder = runner._create_recorder(segment)
        from demorec.modes.terminal import TerminalRecorder

        assert isinstance(recorder, TerminalRecorder)
        runner.cleanup()

    def test_creates_browser_recorder(self):
        """Should create BrowserRecorder for browser mode."""
        plan = Plan()
        runner = Runner(plan)
        segment = Segment(mode="browser")
        recorder = runner._create_recorder(segment)
        from demorec.modes.browser import BrowserRecorder

        assert isinstance(recorder, BrowserRecorder)
        runner.cleanup()

    def test_terminal_recorder_with_size(self):
        """Should pass size to TerminalRecorder."""
        plan = Plan()
        runner = Runner(plan)
        segment = Segment(mode="terminal", size="large")
        recorder = runner._create_recorder(segment)
        assert recorder.size == "large"
        runner.cleanup()

    def test_terminal_recorder_with_rows(self):
        """Should pass rows to TerminalRecorder."""
        plan = Plan()
        runner = Runner(plan)
        segment = Segment(mode="terminal", rows=30)
        recorder = runner._create_recorder(segment)
        # TerminalRecorder stores rows in desired_rows
        assert recorder.desired_rows == 30
        runner.cleanup()

    def test_recorder_uses_plan_dimensions(self):
        """Should use plan width/height/framerate."""
        plan = Plan(width=1920, height=1080, framerate=60)
        runner = Runner(plan)
        segment = Segment(mode="terminal")
        recorder = runner._create_recorder(segment)
        assert recorder.width == 1920
        assert recorder.height == 1080
        assert recorder.framerate == 60
        runner.cleanup()


class TestRunnerUpdateNarrationTimes:
    """Test _update_narration_times method."""

    def test_updates_before_narration(self):
        """Should set start_time before command start."""
        plan = Plan()
        runner = Runner(plan)
        timed = TimedNarration("Test", "before", Path("/tmp/test.mp3"), duration=1.0)
        timed_narrations = {0: timed}
        timestamps = {0: (2.0, 3.0)}  # command starts at 2.0, ends at 3.0
        runner._update_narration_times(timed_narrations, timestamps, offset=0.0)
        # before mode: start_time = cmd_start - duration = 2.0 - 1.0 = 1.0
        assert timed.start_time == 1.0
        runner.cleanup()

    def test_updates_during_narration(self):
        """Should set start_time at command start."""
        plan = Plan()
        runner = Runner(plan)
        timed = TimedNarration("Test", "during", Path("/tmp/test.mp3"), duration=1.0)
        timed_narrations = {0: timed}
        timestamps = {0: (2.0, 3.0)}
        runner._update_narration_times(timed_narrations, timestamps, offset=0.0)
        # during mode: start_time = cmd_start = 2.0
        assert timed.start_time == 2.0
        runner.cleanup()

    def test_updates_after_narration(self):
        """Should set start_time at command end."""
        plan = Plan()
        runner = Runner(plan)
        timed = TimedNarration("Test", "after", Path("/tmp/test.mp3"), duration=1.0)
        timed_narrations = {0: timed}
        timestamps = {0: (2.0, 3.0)}
        runner._update_narration_times(timed_narrations, timestamps, offset=0.0)
        # after mode: start_time = cmd_end = 3.0
        assert timed.start_time == 3.0
        runner.cleanup()

    def test_applies_offset(self):
        """Should add offset to all start times."""
        plan = Plan()
        runner = Runner(plan)
        timed = TimedNarration("Test", "after", Path("/tmp/test.mp3"), duration=1.0)
        timed_narrations = {0: timed}
        timestamps = {0: (2.0, 3.0)}
        runner._update_narration_times(timed_narrations, timestamps, offset=5.0)
        # after mode with offset: start_time = offset + cmd_end = 5.0 + 3.0 = 8.0
        assert timed.start_time == 8.0
        runner.cleanup()

    def test_skips_missing_timestamp(self):
        """Should skip narration if timestamp not found."""
        plan = Plan()
        runner = Runner(plan)
        timed = TimedNarration("Test", "after", Path("/tmp/test.mp3"), duration=1.0)
        timed_narrations = {5: timed}  # cmd_idx 5, but not in timestamps
        timestamps = {0: (2.0, 3.0)}  # only cmd 0
        runner._update_narration_times(timed_narrations, timestamps, offset=0.0)
        # Should not update - start_time stays at default 0.0
        assert timed.start_time == 0.0
        runner.cleanup()


class TestRunnerAttachToSegment:
    """Test _attach_to_segment method."""

    def test_attaches_narration_to_segment(self):
        """Should attach timed narration to segment."""
        plan = Plan()
        runner = Runner(plan)
        segment = Segment(mode="terminal")
        timed = TimedNarration("Test", "before", Path("/tmp/test.mp3"), duration=1.0)
        runner._attach_to_segment(segment, 5, timed)
        assert hasattr(segment, "timed_narrations")
        assert segment.timed_narrations[5] == timed
        runner.cleanup()

    def test_creates_timed_narrations_dict(self):
        """Should create timed_narrations dict if not exists."""
        plan = Plan()
        runner = Runner(plan)
        segment = Segment(mode="terminal")
        timed = TimedNarration("Test", "before", Path("/tmp/test.mp3"), duration=1.0)
        runner._attach_to_segment(segment, 0, timed)
        assert isinstance(segment.timed_narrations, dict)
        runner.cleanup()


class TestRunnerBuildConcatCmd:
    """Test _build_segment_concat_cmd method."""

    def test_builds_ffmpeg_concat_command(self):
        """Should build correct FFmpeg concat command."""
        plan = Plan()
        runner = Runner(plan)
        concat_file = Path("/tmp/concat.txt")
        output = Path("/tmp/output.mp4")
        cmd = runner._build_segment_concat_cmd(concat_file, output)
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert "-f" in cmd
        assert "concat" in cmd
        assert str(concat_file) in cmd
        assert str(output) in cmd
        runner.cleanup()


class TestRunnerCreateProgress:
    """Test _create_progress method."""

    def test_creates_progress_context(self):
        """Should create a Progress context manager."""
        from rich.progress import Progress

        plan = Plan()
        runner = Runner(plan)
        progress = runner._create_progress()
        assert isinstance(progress, Progress)
        runner.cleanup()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
