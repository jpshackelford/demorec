"""Recording modes for demorec."""

import asyncio
import subprocess
import time
from pathlib import Path

from ..parser import Segment


def convert_webm_to_mp4(webm_path: Path, mp4_path: Path):
    """Convert webm to mp4 using FFmpeg."""
    cmd = _build_webm_convert_cmd(webm_path, mp4_path)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg conversion failed: {result.stderr}")


# fmt: off
def _build_webm_convert_cmd(webm_path: Path, mp4_path: Path) -> list[str]:
    """Build FFmpeg command for webm to mp4 conversion."""
    return ["ffmpeg", "-y", "-i", str(webm_path), "-c:v", "libx264",
            "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p", str(mp4_path)]
# fmt: on


class CommandExecutorMixin:
    """Mixin providing shared command execution with timing and narration support."""

    _timed_narrations: dict  # Must be defined by subclass

    async def _execute_command(self, page, cmd):
        """Execute a single command. Must be implemented by subclass."""
        raise NotImplementedError

    async def _execute_commands(self, page, segment: Segment) -> dict[int, tuple[float, float]]:
        """Execute commands with timestamp tracking."""
        timestamps: dict[int, tuple[float, float]] = {}
        start = time.time()

        for idx, cmd in enumerate(segment.commands):
            await self._handle_narration_before(idx)
            cmd_start = time.time() - start
            await self._execute_command(page, cmd)
            timestamps[idx] = (cmd_start, time.time() - start)
            await self._handle_narration_after(idx)

        return timestamps

    async def _handle_narration_before(self, cmd_idx: int):
        """Wait for 'before' narration if present."""
        narration = self._timed_narrations.get(cmd_idx)
        if narration and narration.mode == "before":
            await asyncio.sleep(narration.duration)

    async def _handle_narration_after(self, cmd_idx: int):
        """Wait for 'after' narration if present."""
        narration = self._timed_narrations.get(cmd_idx)
        if narration and narration.mode == "after":
            await asyncio.sleep(narration.duration)
