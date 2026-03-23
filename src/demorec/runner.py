"""Main runner that orchestrates recording across modes."""

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .modes.browser import BrowserRecorder
from .modes.terminal import TerminalRecorder
from .modes import vim as vim_module
from .parser import Plan, Segment
from .tts import get_tts_engine, get_audio_duration

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


def _run_ffmpeg(cmd: list[str], error_msg: str):
    """Run an FFmpeg command, raising RuntimeError on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{error_msg}: {result.stderr}")


def _write_concat_file(file_path: Path, files: list[Path]):
    """Write an FFmpeg concat file list."""
    with open(file_path, "w") as f:
        for item in files:
            f.write(f"file '{item}'\n")


class Runner:
    """Orchestrates recording of a demo script."""

    def __init__(self, plan: Plan):
        self.plan = plan
        self.temp_dir = Path(tempfile.mkdtemp(prefix="demorec_"))
        self.segment_files: list[Path] = []
        self.timed_narrations: list[TimedNarration] = []
        self.has_narration = any(seg.narrations for seg in plan.segments)

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
            self._generate_srt(srt_path)
            progress.update(task, completed=True)

    def _run_audio_phase(self, progress, concat_output: Path):
        """Mix audio or copy final output."""
        if self.timed_narrations:
            task = progress.add_task("Mixing audio...", total=None)
            self._mix_audio_timed(concat_output, self.plan.output)
            progress.update(task, completed=True)
        else:
            shutil.copy(concat_output, self.plan.output)

    def _generate_narration(self):
        """Pre-generate all narration audio clips and get durations."""
        engine = get_tts_engine(self.plan.voice)

        narration_idx = 0
        for segment in self.plan.segments:
            for cmd_idx, narration in segment.narrations.items():
                audio_file = self.temp_dir / f"narration_{narration_idx:03d}.mp3"
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

                # Attach to segment for recorder to use
                if not hasattr(segment, "timed_narrations"):
                    segment.timed_narrations = {}
                segment.timed_narrations[cmd_idx] = timed

                narration_idx += 1

    def _record_segment(self, segment: Segment, output: Path, time_offset: float = 0.0) -> float:
        """Record a single segment.

        Args:
            segment: The segment to record
            output: Output video file path
            time_offset: Starting time offset for this segment

        Returns:
            The duration of the recorded segment in seconds
        """
        timed_narrations = getattr(segment, "timed_narrations", {})

        if segment.mode == "terminal":
            recorder = TerminalRecorder(
                width=self.plan.width,
                height=self.plan.height,
                framerate=self.plan.framerate,
                size=segment.size,
                rows=segment.rows,
            )
        else:
            recorder = BrowserRecorder(
                width=self.plan.width,
                height=self.plan.height,
                framerate=self.plan.framerate,
            )

        timestamps = recorder.record(segment, output, timed_narrations)

        # Update narration start times based on recorded timestamps
        for cmd_idx, timed in timed_narrations.items():
            if cmd_idx in timestamps:
                cmd_start, cmd_end = timestamps[cmd_idx]
                if timed.mode == "before":
                    timed.start_time = time_offset + cmd_start - timed.duration
                elif timed.mode == "during":
                    timed.start_time = time_offset + cmd_start
                elif timed.mode == "after":
                    timed.start_time = time_offset + cmd_end

        return self._get_duration(output)

    def _concat_segments(self, output: Path):
        """Concatenate all segment files using FFmpeg."""
        concat_file = self.temp_dir / "concat.txt"
        _write_concat_file(concat_file, self.segment_files)
        cmd = [
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
        _run_ffmpeg(cmd, "FFmpeg concat failed")

    def _concat_audio_files(self) -> Path:
        """Concatenate all audio files and return the combined path."""
        audio_concat = self.temp_dir / "narration_concat.txt"
        _write_concat_file(audio_concat, self.audio_files)
        combined = self.temp_dir / "narration_combined.mp3"
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(audio_concat),
            "-c",
            "copy",
            str(combined),
        ]
        _run_ffmpeg(cmd, "Audio concat failed")
        return combined

    def _overlay_audio(self, video: Path, audio: Path, output: Path):
        """Overlay audio track onto video."""
        # TODO: Implement proper audio/video sync using durations
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
        _run_ffmpeg(cmd, "Audio mixing failed")

    def _mix_audio(self, video_path: Path, output: Path):
        """Mix narration audio with video."""
        if self.timed_narrations:
            return self._mix_audio_timed(video_path, output)
        shutil.copy(video_path, output)

    def _generate_srt(self, output_path: Path):
        """Generate SRT subtitle file from timed narrations."""

        def format_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

        def split_caption(text: str, max_len: int = 42) -> list[str]:
            if len(text) <= max_len:
                return [text]
            lines = []
            words = text.split()
            current_line = ""
            for word in words:
                if len(current_line) + len(word) + 1 <= max_len:
                    current_line = f"{current_line} {word}".strip()
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
            return lines

        with open(output_path, "w", encoding="utf-8") as f:
            for i, narration in enumerate(self.timed_narrations, 1):
                start = max(0, narration.start_time)
                end = start + narration.duration
                lines = split_caption(narration.text)
                caption_text = "\n".join(lines)
                f.write(f"{i}\n")
                f.write(f"{format_time(start)} --> {format_time(end)}\n")
                f.write(f"{caption_text}\n\n")

    def _mix_audio_timed(self, video_path: Path, output: Path):
        """Mix narration audio with video at correct timestamps."""
        if not self.timed_narrations:
            shutil.copy(video_path, output)
            return

        video_duration = self._get_duration(video_path)

        inputs = ["-i", str(video_path)]
        filter_parts = []

        for i, narration in enumerate(self.timed_narrations):
            inputs.extend(["-i", str(narration.audio_path)])
            delay_ms = int(max(0, narration.start_time) * 1000)
            filter_parts.append(f"[{i + 1}:a]adelay={delay_ms}|{delay_ms}[a{i}]")

        if len(self.timed_narrations) == 1:
            filter_complex = f"{filter_parts[0]}; [a0]apad[aout]"
        else:
            mix_inputs = "".join(f"[a{i}]" for i in range(len(self.timed_narrations)))
            filter_complex = (
                "; ".join(filter_parts)
                + f"; {mix_inputs}amix=inputs={len(self.timed_narrations)}:duration=longest:normalize=0:dropout_transition=0[aout]"
            )

        cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-t",
            str(video_duration),
            str(output),
        ]

        _run_ffmpeg(cmd, "Audio mixing failed")

    def _get_duration(self, media_path: Path) -> float:
        """Get duration of a media file in seconds."""
        import json

        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(media_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        return 0.0

    def cleanup(self):
        """Remove temporary files."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
