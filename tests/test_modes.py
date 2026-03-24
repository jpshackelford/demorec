"""Unit tests for recording modes utilities.

Tests cover:
- CommandExecutorMixin class
- _execute_commands method with timestamp tracking
- Narration timing (before/after modes)
"""

import asyncio
import pytest
from dataclasses import dataclass

from demorec.modes import CommandExecutorMixin
from demorec.parser import Segment, Command


@dataclass
class MockNarration:
    """Mock narration object for testing."""
    mode: str
    duration: float


class MockRecorder(CommandExecutorMixin):
    """Mock recorder implementing CommandExecutorMixin for testing."""

    def __init__(self):
        self._timed_narrations: dict = {}
        self._executed_commands: list = []

    async def _execute_command(self, page, cmd):
        """Record command execution for testing."""
        self._executed_commands.append(cmd)
        await asyncio.sleep(0.01)  # Simulate some work


class TestCommandExecutorMixin:
    """Test CommandExecutorMixin class."""

    @pytest.mark.asyncio
    async def test_execute_commands_returns_timestamps(self):
        """Should return timestamps for every command executed."""
        recorder = MockRecorder()
        segment = Segment(
            mode="terminal",
            commands=[
                Command("Type", ["hello"]),
                Command("Enter", []),
                Command("Sleep", ["0.1"]),
            ],
        )

        timestamps = await recorder._execute_commands(None, segment)

        assert len(timestamps) == 3
        assert 0 in timestamps
        assert 1 in timestamps
        assert 2 in timestamps

    @pytest.mark.asyncio
    async def test_timestamps_are_sequential(self):
        """Command timestamps should be in sequential order."""
        recorder = MockRecorder()
        segment = Segment(
            mode="terminal",
            commands=[
                Command("Type", ["cmd1"]),
                Command("Type", ["cmd2"]),
                Command("Type", ["cmd3"]),
            ],
        )

        timestamps = await recorder._execute_commands(None, segment)

        # Each command end should be >= start
        for idx, (start, end) in timestamps.items():
            assert end >= start

        # Commands should be sequential
        assert timestamps[1][0] >= timestamps[0][1]
        assert timestamps[2][0] >= timestamps[1][1]

    @pytest.mark.asyncio
    async def test_all_commands_executed(self):
        """Should execute all commands in order."""
        recorder = MockRecorder()
        segment = Segment(
            mode="terminal",
            commands=[
                Command("Type", ["first"]),
                Command("Type", ["second"]),
                Command("Type", ["third"]),
            ],
        )

        await recorder._execute_commands(None, segment)

        assert len(recorder._executed_commands) == 3
        assert recorder._executed_commands[0].args == ["first"]
        assert recorder._executed_commands[1].args == ["second"]
        assert recorder._executed_commands[2].args == ["third"]

    @pytest.mark.asyncio
    async def test_before_narration_adds_delay(self):
        """'before' narration should add delay before command execution."""
        recorder = MockRecorder()
        recorder._timed_narrations = {1: MockNarration(mode="before", duration=0.1)}

        segment = Segment(
            mode="terminal",
            commands=[
                Command("Type", ["cmd1"]),
                Command("Type", ["cmd2"]),  # Has "before" narration
            ],
        )

        timestamps = await recorder._execute_commands(None, segment)

        # Gap between cmd1 end and cmd2 start should be >= narration duration
        gap = timestamps[1][0] - timestamps[0][1]
        assert gap >= 0.09  # Allow 10% tolerance

    @pytest.mark.asyncio
    async def test_after_narration_adds_delay(self):
        """'after' narration should add delay after command execution."""
        recorder = MockRecorder()
        recorder._timed_narrations = {0: MockNarration(mode="after", duration=0.1)}

        segment = Segment(
            mode="terminal",
            commands=[
                Command("Type", ["cmd1"]),  # Has "after" narration
                Command("Type", ["cmd2"]),
            ],
        )

        timestamps = await recorder._execute_commands(None, segment)

        # Gap between cmd1 end and cmd2 start should be >= narration duration
        gap = timestamps[1][0] - timestamps[0][1]
        assert gap >= 0.09  # Allow 10% tolerance

    @pytest.mark.asyncio
    async def test_during_narration_does_not_add_delay(self):
        """'during' narration should not add any delays."""
        recorder = MockRecorder()
        recorder._timed_narrations = {0: MockNarration(mode="during", duration=0.5)}

        segment = Segment(
            mode="terminal",
            commands=[
                Command("Type", ["cmd1"]),
                Command("Type", ["cmd2"]),
            ],
        )

        timestamps = await recorder._execute_commands(None, segment)

        # Gap should be minimal (just execution overhead)
        gap = timestamps[1][0] - timestamps[0][1]
        assert gap < 0.05  # Should be much less than narration duration

    @pytest.mark.asyncio
    async def test_empty_segment(self):
        """Should handle empty command list gracefully."""
        recorder = MockRecorder()
        segment = Segment(mode="terminal", commands=[])

        timestamps = await recorder._execute_commands(None, segment)

        assert timestamps == {}

    @pytest.mark.asyncio
    async def test_narration_for_nonexistent_command_ignored(self):
        """Narration for command index that doesn't exist should be ignored."""
        recorder = MockRecorder()
        recorder._timed_narrations = {99: MockNarration(mode="before", duration=1.0)}

        segment = Segment(
            mode="terminal",
            commands=[Command("Type", ["only_cmd"])],
        )

        # This should not raise
        timestamps = await recorder._execute_commands(None, segment)
        assert len(timestamps) == 1


class TestHandleNarrationBefore:
    """Test _handle_narration_before method."""

    @pytest.mark.asyncio
    async def test_waits_for_before_narration(self):
        """Should wait for narration duration if mode is 'before'."""
        recorder = MockRecorder()
        recorder._timed_narrations = {0: MockNarration(mode="before", duration=0.1)}

        start = asyncio.get_event_loop().time()
        await recorder._handle_narration_before(0)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed >= 0.09  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_no_wait_for_after_narration(self):
        """Should not wait if mode is 'after'."""
        recorder = MockRecorder()
        recorder._timed_narrations = {0: MockNarration(mode="after", duration=1.0)}

        start = asyncio.get_event_loop().time()
        await recorder._handle_narration_before(0)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed < 0.05  # Should be nearly instant

    @pytest.mark.asyncio
    async def test_no_wait_if_no_narration(self):
        """Should not wait if no narration at index."""
        recorder = MockRecorder()

        start = asyncio.get_event_loop().time()
        await recorder._handle_narration_before(0)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed < 0.01  # Should be nearly instant


class TestHandleNarrationAfter:
    """Test _handle_narration_after method."""

    @pytest.mark.asyncio
    async def test_waits_for_after_narration(self):
        """Should wait for narration duration if mode is 'after'."""
        recorder = MockRecorder()
        recorder._timed_narrations = {0: MockNarration(mode="after", duration=0.1)}

        start = asyncio.get_event_loop().time()
        await recorder._handle_narration_after(0)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed >= 0.09  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_no_wait_for_before_narration(self):
        """Should not wait if mode is 'before'."""
        recorder = MockRecorder()
        recorder._timed_narrations = {0: MockNarration(mode="before", duration=1.0)}

        start = asyncio.get_event_loop().time()
        await recorder._handle_narration_after(0)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed < 0.05  # Should be nearly instant

    @pytest.mark.asyncio
    async def test_no_wait_if_no_narration(self):
        """Should not wait if no narration at index."""
        recorder = MockRecorder()

        start = asyncio.get_event_loop().time()
        await recorder._handle_narration_after(0)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed < 0.01  # Should be nearly instant


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
