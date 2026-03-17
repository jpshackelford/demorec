"""Main runner that orchestrates recording across modes."""

import subprocess
import tempfile
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .parser import Plan, Segment
from .modes.terminal import TerminalRecorder
from .modes.browser import BrowserRecorder

console = Console()


class Runner:
    """Orchestrates recording of a demo script."""
    
    def __init__(self, plan: Plan):
        self.plan = plan
        self.temp_dir = Path(tempfile.mkdtemp(prefix="demorec_"))
        self.segment_files: list[Path] = []
    
    def run(self):
        """Execute the full recording pipeline."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
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
                self._concat_segments()
                progress.update(task, completed=True)
            else:
                # Single segment - just copy
                import shutil
                shutil.copy(self.segment_files[0], self.plan.output)
    
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
    
    def _concat_segments(self):
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
            str(self.plan.output)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")
    
    def cleanup(self):
        """Remove temporary files."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
