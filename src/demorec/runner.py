"""Main runner that orchestrates recording across modes."""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .parser import Plan, Segment, Narration
from .modes.terminal import TerminalRecorder
from .modes.browser import BrowserRecorder
from .modes import vim as vim_module
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


class Runner:
    """Orchestrates recording of a demo script."""
    
    def __init__(self, plan: Plan):
        self.plan = plan
        self.temp_dir = Path(tempfile.mkdtemp(prefix="demorec_"))
        self.segment_files: list[Path] = []
        self.timed_narrations: list[TimedNarration] = []  # All narrations with timing
        self.has_narration = any(
            seg.narrations for seg in plan.segments
        )
    
    def _uses_vim_primitives(self) -> bool:
        """Check if any segment uses high-level vim primitives."""
        vim_commands = {"Open", "Highlight", "Close", "Goto"}
        for segment in self.plan.segments:
            for cmd in segment.commands:
                if cmd.name in vim_commands:
                    return True
        return False
    
    def _run_preflight_checks(self) -> list[str]:
        """Run preflight checks before recording.
        
        Returns list of error messages (empty if all checks pass).
        """
        errors = []
        
        # Check vim if needed
        if self._uses_vim_primitives():
            errors.extend(vim_module.preflight_check())
        
        return errors
    
    def run(self):
        """Execute the full recording pipeline."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Run preflight checks before anything else
            task = progress.add_task("Running preflight checks...", total=None)
            errors = self._run_preflight_checks()
            if errors:
                progress.update(task, completed=True)
                for error in errors:
                    console.print(f"[red]Preflight error:[/red] {error}")
                raise RuntimeError("Preflight checks failed")
            progress.update(task, completed=True)
            
            # Generate narration audio if needed
            if self.has_narration and self.plan.voice:
                task = progress.add_task("Generating narration audio...", total=None)
                self._generate_narration()
                progress.update(task, completed=True)
            
            # Record each segment, tracking time offsets
            time_offset = 0.0
            for i, segment in enumerate(self.plan.segments):
                task = progress.add_task(
                    f"Recording segment {i+1}/{len(self.plan.segments)} ({segment.mode})...",
                    total=None
                )
                
                segment_file = self.temp_dir / f"segment_{i:03d}.mp4"
                segment_duration = self._record_segment(segment, segment_file, time_offset)
                self.segment_files.append(segment_file)
                time_offset += segment_duration
                
                progress.update(task, completed=True)
            
            # Concatenate segments
            if len(self.segment_files) > 1:
                task = progress.add_task("Concatenating segments...", total=None)
                concat_output = self.temp_dir / "concat.mp4"
                self._concat_segments(concat_output)
                progress.update(task, completed=True)
            else:
                concat_output = self.segment_files[0]
            
            # Generate SRT subtitles if we have narration
            srt_path = None
            if self.timed_narrations:
                task = progress.add_task("Generating subtitles...", total=None)
                srt_path = self.plan.output.with_suffix('.srt')
                self._generate_srt(srt_path)
                progress.update(task, completed=True)
            
            # Add audio if we have narration
            if self.timed_narrations:
                task = progress.add_task("Mixing audio...", total=None)
                self._mix_audio_timed(concat_output, self.plan.output)
                progress.update(task, completed=True)
            else:
                import shutil
                shutil.copy(concat_output, self.plan.output)
    
    def _generate_narration(self):
        """Pre-generate all narration audio clips and get durations."""
        engine = get_tts_engine(self.plan.voice)
        
        narration_idx = 0
        for seg_idx, segment in enumerate(self.plan.segments):
            for cmd_idx, narration in segment.narrations.items():
                audio_file = self.temp_dir / f"narration_{narration_idx:03d}.mp3"
                engine.synthesize(narration.text, audio_file)
                
                # Get actual audio duration
                duration = get_audio_duration(audio_file)
                
                # Store with timing info
                timed = TimedNarration(
                    text=narration.text,
                    mode=narration.mode,
                    audio_path=audio_file,
                    duration=duration,
                    cmd_index=cmd_idx,
                )
                self.timed_narrations.append(timed)
                
                # Also store in segment for recorder to access
                if not hasattr(segment, 'timed_narrations'):
                    segment.timed_narrations = {}
                segment.timed_narrations[cmd_idx] = timed
                
                narration_idx += 1
    
    def _record_segment(self, segment: Segment, output: Path, time_offset: float = 0.0) -> float:
        """Record a single segment.
        
        Args:
            segment: The segment to record
            output: Output video file path
            time_offset: Starting time offset for this segment (for multi-segment timing)
            
        Returns:
            The duration of the recorded segment in seconds
        """
        # Get timed narrations for this segment (if any)
        timed_narrations = getattr(segment, 'timed_narrations', {})
        
        if segment.mode == "terminal":
            recorder = TerminalRecorder(
                width=self.plan.width,
                height=self.plan.height,
                framerate=self.plan.framerate,
                size=segment.size,
                rows=segment.rows,  # Explicit row count (overrides size preset)
            )
        else:
            recorder = BrowserRecorder(
                width=self.plan.width,
                height=self.plan.height,
                framerate=self.plan.framerate,
            )
        
        # Record and get command timestamps
        timestamps = recorder.record(segment, output, timed_narrations)
        
        # Update narration start times based on recorded timestamps
        for cmd_idx, timed in timed_narrations.items():
            if cmd_idx in timestamps:
                cmd_start, cmd_end = timestamps[cmd_idx]
                if timed.mode == "before":
                    # Narration plays before command, so it starts at cmd_start - duration
                    # But since we add delay in recorder, narration starts at cmd_start - duration
                    timed.start_time = time_offset + cmd_start - timed.duration
                elif timed.mode == "during":
                    # Narration plays during command
                    timed.start_time = time_offset + cmd_start
                elif timed.mode == "after":
                    # Narration plays after command
                    timed.start_time = time_offset + cmd_end
        
        # Return segment duration
        return self._get_duration(output)
    
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
    
    def _generate_srt(self, output_path: Path):
        """Generate SRT subtitle file from timed narrations."""
        
        def format_time(seconds: float) -> str:
            """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        
        def split_caption(text: str, max_len: int = 42) -> list[str]:
            """Split long captions at word boundaries for readability."""
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
                start = max(0, narration.start_time)  # Ensure non-negative
                end = start + narration.duration
                
                # Split long captions
                lines = split_caption(narration.text)
                caption_text = "\n".join(lines)
                
                f.write(f"{i}\n")
                f.write(f"{format_time(start)} --> {format_time(end)}\n")
                f.write(f"{caption_text}\n\n")
    
    def _mix_audio_timed(self, video_path: Path, output: Path):
        """Mix narration audio with video at correct timestamps."""
        if not self.timed_narrations:
            import shutil
            shutil.copy(video_path, output)
            return
        
        video_duration = self._get_duration(video_path)
        
        # Build FFmpeg filter for mixing multiple audio tracks at specific times
        # We use the adelay filter to position each narration
        
        inputs = ["-i", str(video_path)]
        filter_parts = []
        
        for i, narration in enumerate(self.timed_narrations):
            inputs.extend(["-i", str(narration.audio_path)])
            # adelay takes milliseconds
            delay_ms = int(max(0, narration.start_time) * 1000)
            filter_parts.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[a{i}]")
        
        # Mix all delayed audio tracks together
        # Use normalize=0 to prevent volume reduction, and dropout_transition=0
        # to avoid volume changes as tracks end (our narrations are sequential, not overlapping)
        if len(self.timed_narrations) == 1:
            filter_complex = f"{filter_parts[0]}; [a0]apad[aout]"
        else:
            mix_inputs = "".join(f"[a{i}]" for i in range(len(self.timed_narrations)))
            # normalize=0 keeps consistent volume for sequential (non-overlapping) audio
            filter_complex = "; ".join(filter_parts) + f"; {mix_inputs}amix=inputs={len(self.timed_narrations)}:duration=longest:normalize=0:dropout_transition=0[aout]"
        
        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-t", str(video_duration),  # Limit to video duration
            str(output)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Audio mixing failed: {result.stderr}")
    
    def _mix_audio(self, video_path: Path, output: Path):
        """Legacy audio mixing - concatenate and overlay."""
        # Redirect to timed mixing if we have timed narrations
        if self.timed_narrations:
            return self._mix_audio_timed(video_path, output)
        
        import shutil
        shutil.copy(video_path, output)
    
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
        """Remove temporary files."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
