"""Unit tests for recording utilities and timing accuracy."""

import asyncio
import pytest
from dataclasses import dataclass

from demorec.modes.recording import CommandTimestamps, execute_with_narration_timing


class TestCommandTimestamps:
    """Test CommandTimestamps class."""

    def test_start_recording_resets_state(self):
        """start_recording should clear timestamps and set start time."""
        tracker = CommandTimestamps()
        tracker.record_command(0, 1.0, 2.0)
        
        tracker.start_recording()
        
        assert tracker.get_timestamps() == {}

    def test_record_command_stores_relative_times(self):
        """record_command should store times relative to recording start."""
        tracker = CommandTimestamps()
        tracker._start_time = 100.0  # Simulate start at t=100
        
        tracker.record_command(0, 100.5, 101.0)  # Absolute times
        
        timestamps = tracker.get_timestamps()
        assert timestamps[0] == (0.5, 1.0)  # Relative times

    def test_get_timestamps_returns_copy(self):
        """get_timestamps should return a copy, not the internal dict."""
        tracker = CommandTimestamps()
        tracker._start_time = 0.0
        tracker.record_command(0, 0.0, 1.0)
        
        result = tracker.get_timestamps()
        result[99] = (99.0, 100.0)  # Modify the returned dict
        
        assert 99 not in tracker.get_timestamps()  # Original unchanged


@dataclass
class MockNarration:
    """Mock narration object for testing."""
    mode: str
    duration: float


class TestExecuteWithNarrationTiming:
    """Test execute_with_narration_timing function."""

    @pytest.mark.asyncio
    async def test_returns_timestamps_for_all_commands(self):
        """Should return timestamps for every command executed."""
        commands = ["cmd1", "cmd2", "cmd3"]
        
        async def execute_fn(cmd):
            await asyncio.sleep(0.01)
        
        timestamps = await execute_with_narration_timing(
            commands=commands,
            timed_narrations={},
            execute_fn=execute_fn,
        )
        
        assert len(timestamps) == 3
        assert 0 in timestamps
        assert 1 in timestamps
        assert 2 in timestamps

    @pytest.mark.asyncio
    async def test_timestamps_are_sequential(self):
        """Command timestamps should be in sequential order."""
        commands = ["cmd1", "cmd2", "cmd3"]
        
        async def execute_fn(cmd):
            await asyncio.sleep(0.02)
        
        timestamps = await execute_with_narration_timing(
            commands=commands,
            timed_narrations={},
            execute_fn=execute_fn,
        )
        
        # Each command should start after the previous one ends
        assert timestamps[1][0] >= timestamps[0][1]
        assert timestamps[2][0] >= timestamps[1][1]

    @pytest.mark.asyncio
    async def test_before_narration_adds_delay_before_command(self):
        """'before' narration should delay command execution."""
        commands = ["cmd1", "cmd2"]
        narration_duration = 0.1
        
        async def execute_fn(cmd):
            await asyncio.sleep(0.01)
        
        timestamps = await execute_with_narration_timing(
            commands=commands,
            timed_narrations={1: MockNarration(mode="before", duration=narration_duration)},
            execute_fn=execute_fn,
        )
        
        # Gap between cmd1 end and cmd2 start should be >= narration duration
        gap = timestamps[1][0] - timestamps[0][1]
        assert gap >= narration_duration * 0.9  # Allow 10% tolerance

    @pytest.mark.asyncio
    async def test_after_narration_adds_delay_after_command(self):
        """'after' narration should add delay after command execution."""
        commands = ["cmd1", "cmd2"]
        narration_duration = 0.1
        
        async def execute_fn(cmd):
            await asyncio.sleep(0.01)
        
        timestamps = await execute_with_narration_timing(
            commands=commands,
            timed_narrations={0: MockNarration(mode="after", duration=narration_duration)},
            execute_fn=execute_fn,
        )
        
        # Gap between cmd1 end and cmd2 start should be >= narration duration
        gap = timestamps[1][0] - timestamps[0][1]
        assert gap >= narration_duration * 0.9  # Allow 10% tolerance

    @pytest.mark.asyncio
    async def test_during_narration_does_not_add_delay(self):
        """'during' narration should not add any delays."""
        commands = ["cmd1", "cmd2"]
        
        async def execute_fn(cmd):
            await asyncio.sleep(0.01)
        
        # With 'during', no delay should be added
        timestamps = await execute_with_narration_timing(
            commands=commands,
            timed_narrations={0: MockNarration(mode="during", duration=0.5)},
            execute_fn=execute_fn,
        )
        
        # Gap should be minimal (just execution overhead)
        gap = timestamps[1][0] - timestamps[0][1]
        assert gap < 0.05  # Should be much less than narration duration

    @pytest.mark.asyncio
    async def test_command_execution_time_is_accurate(self):
        """Command duration in timestamps should reflect actual execution time."""
        commands = ["cmd1"]
        expected_duration = 0.1
        
        async def execute_fn(cmd):
            await asyncio.sleep(expected_duration)
        
        timestamps = await execute_with_narration_timing(
            commands=commands,
            timed_narrations={},
            execute_fn=execute_fn,
        )
        
        actual_duration = timestamps[0][1] - timestamps[0][0]
        # Allow 20% tolerance for timing variability
        assert abs(actual_duration - expected_duration) < expected_duration * 0.2

    @pytest.mark.asyncio
    async def test_multiple_narrations_cumulative_delay(self):
        """Multiple narrations should add cumulative delays."""
        commands = ["cmd1", "cmd2", "cmd3"]
        delay1 = 0.05
        delay2 = 0.05
        
        async def execute_fn(cmd):
            await asyncio.sleep(0.01)
        
        timestamps = await execute_with_narration_timing(
            commands=commands,
            timed_narrations={
                0: MockNarration(mode="after", duration=delay1),
                1: MockNarration(mode="before", duration=delay2),
            },
            execute_fn=execute_fn,
        )
        
        # Gap between cmd1 and cmd2 should include both delays
        gap = timestamps[1][0] - timestamps[0][1]
        assert gap >= (delay1 + delay2) * 0.9

    @pytest.mark.asyncio
    async def test_empty_commands_returns_empty_dict(self):
        """Should handle empty command list gracefully."""
        async def execute_fn(cmd):
            pass
        
        timestamps = await execute_with_narration_timing(
            commands=[],
            timed_narrations={},
            execute_fn=execute_fn,
        )
        
        assert timestamps == {}

    @pytest.mark.asyncio
    async def test_narration_for_nonexistent_command_ignored(self):
        """Narration for command index that doesn't exist should be ignored."""
        commands = ["cmd1"]
        
        async def execute_fn(cmd):
            await asyncio.sleep(0.01)
        
        # This should not raise, narration for cmd index 99 is just ignored
        timestamps = await execute_with_narration_timing(
            commands=commands,
            timed_narrations={99: MockNarration(mode="before", duration=1.0)},
            execute_fn=execute_fn,
        )
        
        assert len(timestamps) == 1
