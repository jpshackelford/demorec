"""Shared recording utilities for terminal and browser modes."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any


@dataclass
class CommandTimestamps:
    """Tracks command execution timestamps during recording."""
    
    _start_time: float = field(default=0.0, init=False)
    _timestamps: dict[int, tuple[float, float]] = field(default_factory=dict, init=False)
    
    def start_recording(self) -> None:
        """Mark the start of recording."""
        self._start_time = time.time()
        self._timestamps.clear()
    
    def record_command(self, cmd_idx: int, start: float, end: float) -> None:
        """Record start/end times for a command (relative to recording start)."""
        self._timestamps[cmd_idx] = (start - self._start_time, end - self._start_time)
    
    def get_timestamps(self) -> dict[int, tuple[float, float]]:
        """Get all recorded timestamps."""
        return self._timestamps.copy()


async def execute_with_narration_timing(
    commands: list,
    timed_narrations: dict,
    execute_fn: Callable[[Any], Awaitable[None]],
) -> dict[int, tuple[float, float]]:
    """Execute commands with narration timing and timestamp tracking.
    
    This is the shared loop used by both terminal and browser recorders.
    
    Args:
        commands: List of commands to execute
        timed_narrations: Dict mapping cmd_index to TimedNarration objects
        execute_fn: Async function to execute a single command
        
    Returns:
        Dict mapping command index to (start_time, end_time) in seconds
    """
    tracker = CommandTimestamps()
    tracker.start_recording()
    
    for cmd_idx, cmd in enumerate(commands):
        narration = timed_narrations.get(cmd_idx)
        
        # Handle "before" narration - add delay before command
        if narration and narration.mode == "before":
            await asyncio.sleep(narration.duration)
        
        # Record command start time
        cmd_start = time.time()
        
        # Execute the command
        await execute_fn(cmd)
        
        # Record command end time
        cmd_end = time.time()
        tracker.record_command(cmd_idx, cmd_start, cmd_end)
        
        # Handle "after" narration - add delay after command
        if narration and narration.mode == "after":
            await asyncio.sleep(narration.duration)
    
    return tracker.get_timestamps()
