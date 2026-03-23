"""Main runner that orchestrates recording across modes."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .modes.browser import BrowserRecorder
from .modes.terminal import TerminalRecorder
from .parser import Plan, Segment
from .tts import get_tts_engine

console = Console()


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
        self.audio_files: list[Path] = []
        self.has_narration = any(seg.narrations for seg in plan.segments)

    def run(self):
        """Execute the full recording pipeline."""
        with self._create_progress() as progress:
            self._run_narration_phase(progress)
            self._run_recording_phase(progress)
            concat_output = self._run_concat_phase(progress)
            self._run_audio_phase(progress, concat_output)

    def _create_progress(self):
        """Create a progress display context."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        )

    def _run_narration_phase(self, progress):
        """Generate narration audio if needed."""
        if self.has_narration and self.plan.voice:
            task = progress.add_task("Generating narration audio...", total=None)
            self._generate_narration()
            progress.update(task, completed=True)

    def _run_recording_phase(self, progress):
        """Record all segments."""
        for i, segment in enumerate(self.plan.segments):
            desc = f"Recording segment {i + 1}/{len(self.plan.segments)} ({segment.mode})..."
            task = progress.add_task(desc, total=None)
            segment_file = self.temp_dir / f"segment_{i:03d}.mp4"
            self._record_segment(segment, segment_file)
            self.segment_files.append(segment_file)
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

    def _run_audio_phase(self, progress, concat_output: Path):
        """Mix audio or copy final output."""
        if self.audio_files:
            task = progress.add_task("Mixing audio...", total=None)
            self._mix_audio(concat_output, self.plan.output)
            progress.update(task, completed=True)
        else:
            shutil.copy(concat_output, self.plan.output)

    def _generate_narration(self):
        """Pre-generate all narration audio clips."""
        engine = get_tts_engine(self.plan.voice)

        narration_idx = 0
        for segment in self.plan.segments:
            for cmd_idx, narration in segment.narrations.items():
                audio_file = self.temp_dir / f"narration_{narration_idx:03d}.mp3"
                engine.synthesize(narration.text, audio_file)
                self.audio_files.append(audio_file)
                narration_idx += 1

    def _record_segment(self, segment: Segment, output: Path):
        """Record a single segment."""
        if segment.mode == "terminal":
            recorder = TerminalRecorder(
                width=self.plan.width,
                height=self.plan.height,
                framerate=self.plan.framerate,
            )
        else:
            recorder = BrowserRecorder(
                width=self.plan.width,
                height=self.plan.height,
                framerate=self.plan.framerate,
            )

        recorder.record(segment, output)

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
        if not self.audio_files:
            shutil.copy(video_path, output)
            return
        combined_audio = self._concat_audio_files()
        self._overlay_audio(video_path, combined_audio, output)

    def cleanup(self):
        """Remove temporary files."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
