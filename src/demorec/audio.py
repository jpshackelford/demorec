"""Audio and video processing utilities using FFmpeg.

Provides functions for mixing, concatenating, and processing audio/video files.
"""

import json
import shutil
import subprocess
from pathlib import Path


def run_ffmpeg(cmd: list[str], error_msg: str):
    """Run an FFmpeg command, raising RuntimeError on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{error_msg}: {result.stderr}")


def write_concat_file(file_path: Path, files: list[Path]):
    """Write an FFmpeg concat file list."""
    with open(file_path, "w") as f:
        for item in files:
            f.write(f"file '{item}'\n")


def get_duration(media_path: Path) -> float:
    """Get duration of a media file in seconds."""
    cmd = _build_probe_cmd(media_path)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return _parse_duration(result) if result.returncode == 0 else 0.0


def _build_probe_cmd(media_path: Path) -> list[str]:
    """Build ffprobe command."""
    return ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(media_path)]


def _parse_duration(result) -> float:
    """Parse duration from ffprobe result."""
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration", 0))


def concat_audio_files(audio_files: list[Path], output: Path, temp_dir: Path) -> Path:
    """Concatenate multiple audio files into one."""
    concat_file = temp_dir / "narration_concat.txt"
    write_concat_file(concat_file, audio_files)
    cmd = _build_concat_cmd(concat_file, output)
    run_ffmpeg(cmd, "Audio concat failed")
    return output


# fmt: off
def _build_concat_cmd(concat_file: Path, output: Path) -> list[str]:
    """Build FFmpeg concat command."""
    return ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-c", "copy", str(output)]
# fmt: on


def overlay_audio(video: Path, audio: Path, output: Path):
    """Overlay audio track onto video."""
    cmd = _build_overlay_cmd(video, audio, output)
    run_ffmpeg(cmd, "Audio overlay failed")


# fmt: off
def _build_overlay_cmd(video: Path, audio: Path, output: Path) -> list[str]:
    """Build FFmpeg overlay command."""
    return ["ffmpeg", "-y", "-i", str(video), "-i", str(audio),
            "-c:v", "copy", "-c:a", "aac", "-shortest", str(output)]
# fmt: on


def mix_audio_timed(video_path: Path, narrations: list, output: Path):
    """Mix narration audio with video at correct timestamps."""
    if not narrations:
        shutil.copy(video_path, output)
        return

    cmd = _build_mix_command(video_path, narrations, output)
    run_ffmpeg(cmd, "Audio mixing failed")


# fmt: off
def _build_mix_command(video_path: Path, narrations: list, output: Path) -> list[str]:
    """Build FFmpeg command for audio mixing."""
    inputs = _build_input_args(video_path, narrations)
    dur = str(get_duration(video_path))
    return ["ffmpeg", "-y", *inputs, "-filter_complex", _build_audio_filter(narrations),
            "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-t", dur, str(output)]
# fmt: on


def _build_input_args(video_path: Path, narrations: list) -> list[str]:
    """Build FFmpeg input arguments."""
    inputs = ["-i", str(video_path)]
    for n in narrations:
        inputs.extend(["-i", str(n.audio_path)])
    return inputs


def _build_audio_filter(narrations: list) -> str:
    """Build FFmpeg filter_complex for mixing narrations."""
    filter_parts = []

    for i, n in enumerate(narrations):
        delay_ms = int(max(0, n.start_time) * 1000)
        filter_parts.append(f"[{i + 1}:a]adelay={delay_ms}|{delay_ms}[a{i}]")

    if len(narrations) == 1:
        return f"{filter_parts[0]}; [a0]apad[aout]"

    mix_inputs = "".join(f"[a{i}]" for i in range(len(narrations)))
    amix_opts = "duration=longest:normalize=0:dropout_transition=0"
    amix_filter = f"{mix_inputs}amix=inputs={len(narrations)}:{amix_opts}[aout]"
    return "; ".join(filter_parts) + f"; {amix_filter}"


def format_srt_time(seconds: float) -> str:
    """Format time in SRT format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def split_caption(text: str, max_len: int = 42) -> list[str]:
    """Split caption text into lines of max_len characters."""
    if len(text) <= max_len:
        return [text]
    return _word_wrap(text.split(), max_len)


def _word_wrap(words: list[str], max_len: int) -> list[str]:
    """Wrap words into lines of max_len."""
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 <= max_len:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_srt(narrations: list, output_path: Path):
    """Generate SRT subtitle file from timed narrations.

    Args:
        narrations: List of objects with text, start_time, duration
        output_path: Output SRT file path
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for i, n in enumerate(narrations, 1):
            start = max(0, n.start_time)
            end = start + n.duration
            lines = split_caption(n.text)
            caption_text = "\n".join(lines)

            f.write(f"{i}\n")
            f.write(f"{format_srt_time(start)} --> {format_srt_time(end)}\n")
            f.write(f"{caption_text}\n\n")
