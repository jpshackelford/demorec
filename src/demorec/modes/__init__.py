"""Recording modes for demorec."""

import subprocess
from pathlib import Path


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
