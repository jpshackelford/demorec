"""Main runner that orchestrates recording across modes."""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .audio import (
    generate_srt,
    get_duration,
    mix_audio_timed,
    run_ffmpeg,
    write_concat_file,
)
from .modes import vim as vim_module
from .modes.browser import BrowserRecorder
from .modes.terminal import TerminalRecorder, TerminalSessionManager
from .parser import Plan, Segment
from .tts import get_audio_duration, get_tts_engine

console = Console()


@dataclass
class TimedNarration:
    """A narration with timing information."""

    text: str
    mode: str  # before, during, after
    audio_path: Path
    duration: float  # audio duration in seconds
    start_time: float = 0.0  # when to start playing (set during recording)
    cmd_index: int = 0  # which command this is attached to


class Runner:
    """Orchestrates recording of a demo script."""

    def __init__(self, plan: Plan):
        self.plan = plan
        self.temp_dir = Path(tempfile.mkdtemp(prefix="demorec_"))
        self.segment_files: list[Path] = []
        self.timed_narrations: list[TimedNarration] = []
        self.has_narration = any(seg.narrations for seg in plan.segments)
        # Session manager for persistent terminal sessions across mode switches
        self._session_manager = TerminalSessionManager()

    def _uses_vim_primitives(self) -> bool:
        """Check if any segment uses high-level vim primitives."""
        vim_commands = {"Open", "Highlight", "Close", "Goto"}
        for segment in self.plan.segments:
            for cmd in segment.commands:
                if cmd.name in vim_commands:
                    return True
        return False

    def _run_preflight_checks(self) -> list[str]:
        """Run preflight checks before recording."""
        errors = []
        if self._uses_vim_primitives():
            errors.extend(vim_module.preflight_check())
        return errors

    def run(self):
        """Execute the full recording pipeline."""
        with self._create_progress() as progress:
            self._run_preflight_phase(progress)
            self._run_narration_phase(progress)
            self._run_recording_phase(progress)
            concat_output = self._run_concat_phase(progress)
            self._run_subtitle_phase(progress)
            self._run_audio_phase(progress, concat_output)

    def _create_progress(self):
        """Create a progress display context."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        )

    def _run_preflight_phase(self, progress):
        """Run preflight checks before recording."""
        task = progress.add_task("Running preflight checks...", total=None)
        errors = self._run_preflight_checks()
        if errors:
            progress.update(task, completed=True)
            for error in errors:
                console.print(f"[red]Preflight error:[/red] {error}")
            raise RuntimeError("Preflight checks failed")
        progress.update(task, completed=True)

    def _run_narration_phase(self, progress):
        """Generate narration audio if needed."""
        if self.has_narration and self.plan.voice:
            task = progress.add_task("Generating narration audio...", total=None)
            self._generate_narration()
            progress.update(task, completed=True)

    def _run_recording_phase(self, progress):
        """Record all segments."""
        time_offset = 0.0
        for i, segment in enumerate(self.plan.segments):
            desc = f"Recording segment {i + 1}/{len(self.plan.segments)} ({segment.mode})..."
            task = progress.add_task(desc, total=None)
            segment_file = self.temp_dir / f"segment_{i:03d}.mp4"
            segment_duration = self._record_segment(segment, segment_file, time_offset)
            self.segment_files.append(segment_file)
            time_offset += segment_duration
            progress.update(task, completed=True)

    def _run_concat_phase(self, progress) -> Path:
        """Concatenate segments if needed, return output path."""
        if len(self.segment_files) > 1:
            task = progress.add_task("Concatenating segments...", total=None)
            concat_output = self.temp_dir / "concat.mp4"
            self._concat_segments(concat_output)
            progress.update(task, completed=True)
            return concat_output
        return self.segment_files[0]

    def _run_subtitle_phase(self, progress):
        """Generate SRT subtitles if we have narration."""
        if self.timed_narrations:
            task = progress.add_task("Generating subtitles...", total=None)
            srt_path = self.plan.output.with_suffix(".srt")
            generate_srt(self.timed_narrations, srt_path)
            progress.update(task, completed=True)

    def _run_audio_phase(self, progress, concat_output: Path):
        """Mix audio or copy final output."""
        if self.timed_narrations:
            task = progress.add_task("Mixing audio...", total=None)
            mix_audio_timed(concat_output, self.timed_narrations, self.plan.output)
            progress.update(task, completed=True)
        else:
            shutil.copy(concat_output, self.plan.output)

    def _generate_narration(self):
        """Pre-generate all narration audio clips and get durations."""
        engine = get_tts_engine(self.plan.voice)
        narration_idx = 0

        for segment in self.plan.segments:
            for cmd_idx, narration in segment.narrations.items():
                timed = self._synthesize_narration(engine, narration, cmd_idx, narration_idx)
                self._attach_to_segment(segment, cmd_idx, timed)
                narration_idx += 1

    def _synthesize_narration(self, engine, narration, cmd_idx: int, idx: int) -> "TimedNarration":
        """Synthesize a single narration and return TimedNarration."""
        audio_file = self.temp_dir / f"narration_{idx:03d}.mp3"
        engine.synthesize(narration.text, audio_file)
        duration = get_audio_duration(audio_file)

        timed = TimedNarration(
            text=narration.text,
            mode=narration.mode,
            audio_path=audio_file,
            duration=duration,
            cmd_index=cmd_idx,
        )
        self.timed_narrations.append(timed)
        return timed

    def _attach_to_segment(self, segment: Segment, cmd_idx: int, timed: "TimedNarration"):
        """Attach timed narration to segment for recorder."""
        segment.timed_narrations[cmd_idx] = timed

    def _record_segment(self, segment: Segment, output: Path, time_offset: float = 0.0) -> float:
        """Record a single segment and return its duration."""
        timed_narrations = segment.timed_narrations
        recorder = self._create_recorder(segment)
        timestamps = recorder.record(segment, output, timed_narrations)
        self._update_narration_times(timed_narrations, timestamps, time_offset)
        return get_duration(output)

    def _create_recorder(self, segment: Segment):
        """Create appropriate recorder for segment mode."""
        base = dict(width=self.plan.width, height=self.plan.height, framerate=self.plan.framerate)
        if segment.mode == "terminal":
            return TerminalRecorder(
                **base,
                size=segment.size,
                rows=segment.rows,
                session_manager=self._session_manager,
                session_name=segment.session_name,
            )
        return BrowserRecorder(**base)

    def _update_narration_times(self, timed_narrations: dict, timestamps: dict, offset: float):
        """Update narration start times based on recorded timestamps."""
        for cmd_idx, timed in timed_narrations.items():
            if cmd_idx not in timestamps:
                continue
            cmd_start, cmd_end = timestamps[cmd_idx]
            if timed.mode == "before":
                timed.start_time = offset + cmd_start - timed.duration
            elif timed.mode == "during":
                timed.start_time = offset + cmd_start
            elif timed.mode == "after":
                timed.start_time = offset + cmd_end

    def _concat_segments(self, output: Path):
        """Concatenate all segment files using FFmpeg."""
        concat_file = self.temp_dir / "concat.txt"
        write_concat_file(concat_file, self.segment_files)
        cmd = self._build_segment_concat_cmd(concat_file, output)
        run_ffmpeg(cmd, "FFmpeg concat failed")

    def _build_segment_concat_cmd(self, concat_file: Path, output: Path) -> list[str]:  # length-ok
        """Build FFmpeg segment concat command."""
        return [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output),
        ]

    def cleanup(self):
        """Remove temporary files and stop all terminal sessions."""
        # Stop terminal sessions first (must run even if temp cleanup fails)
        try:
            self._session_manager.cleanup()
        finally:
            # Remove temporary files
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
