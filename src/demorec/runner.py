"""Main runner that orchestrates recording across modes."""

import subprocess
import tempfile
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .parser import Plan, Segment, Narration
from .modes.terminal import TerminalRecorder, TerminalSessionManager
from .modes.browser import BrowserRecorder
from .tts import get_tts_engine, get_audio_duration

console = Console()


class Runner:
    """Orchestrates recording of a demo script."""
    
    def __init__(self, plan: Plan):
        self.plan = plan
        self.temp_dir = Path(tempfile.mkdtemp(prefix="demorec_"))
        self.segment_files: list[Path] = []
        self.audio_files: list[Path] = []
        self.has_narration = any(
            seg.narrations for seg in plan.segments
        )
        # Session manager for persistent terminal sessions
        self.session_manager = TerminalSessionManager()
    
    def run(self):
        """Execute the full recording pipeline."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Generate narration audio if needed
            if self.has_narration and self.plan.voice:
                task = progress.add_task("Generating narration audio...", total=None)
                self._generate_narration()
                progress.update(task, completed=True)
            
            # Record each segment
            for i, segment in enumerate(self.plan.segments):
                task = progress.add_task(
                    f"Recording segment {i+1}/{len(self.plan.segments)} ({segment.mode})...",
                    total=None
                )
                
                segment_file = self.temp_dir / f"segment_{i:03d}.mp4"
                self._record_segment(segment, segment_file)
                self.segment_files.append(segment_file)
                
                progress.update(task, completed=True)
            
            # Concatenate segments
            if len(self.segment_files) > 1:
                task = progress.add_task("Concatenating segments...", total=None)
                concat_output = self.temp_dir / "concat.mp4"
                self._concat_segments(concat_output)
                progress.update(task, completed=True)
            else:
                concat_output = self.segment_files[0]
            
            # Add audio if we have narration
            if self.audio_files:
                task = progress.add_task("Mixing audio...", total=None)
                self._mix_audio(concat_output, self.plan.output)
                progress.update(task, completed=True)
            else:
                import shutil
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
                session_manager=self.session_manager,
                session_name=segment.session_name,
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
        # Create concat file list
        concat_file = self.temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for seg_file in self.segment_files:
                f.write(f"file '{seg_file}'\n")
        
        # Run FFmpeg concat
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")
    
    def _mix_audio(self, video_path: Path, output: Path):
        """Mix narration audio with video.
        
        For now, we concatenate all narration files and overlay on video.
        TODO: Proper timing based on narration mode (before/during/after).
        """
        if not self.audio_files:
            import shutil
            shutil.copy(video_path, output)
            return
        
        # Concatenate all audio files
        audio_concat = self.temp_dir / "narration_concat.txt"
        with open(audio_concat, "w") as f:
            for audio_file in self.audio_files:
                f.write(f"file '{audio_file}'\n")
        
        combined_audio = self.temp_dir / "narration_combined.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(audio_concat),
            "-c", "copy",
            str(combined_audio)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Audio concat failed: {result.stderr}")
        
        # Get durations
        video_duration = self._get_duration(video_path)
        audio_duration = self._get_duration(combined_audio)
        
        # If audio is longer than video, we need to extend video
        # For now, just overlay what we have
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(combined_audio),
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",  # Use shorter of the two
            str(output)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Audio mixing failed: {result.stderr}")
    
    def _get_duration(self, media_path: Path) -> float:
        """Get duration of a media file in seconds."""
        import json
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(media_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return 0.0
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    
    def cleanup(self):
        """Remove temporary files and stop terminal sessions."""
        import shutil
        # Stop all terminal sessions
        self.session_manager.cleanup()
        # Remove temp files
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
