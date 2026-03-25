"""Marp CLI integration for rendering presentations."""

import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

THEME_ALIASES = {
    "openhands": "https://raw.githubusercontent.com/jpshackelford/marp-intro/main/openhands-theme/openhands.css",
}


def check_marp_installed() -> bool:
    """Check if marp CLI is available."""
    return shutil.which("marp") is not None


def is_url(path: str) -> bool:
    """Check if a path is an HTTP(S) URL."""
    return path.startswith(("http://", "https://"))


def download_file(url: str, output_dir: Path, filename: str | None = None) -> Path:
    """Download a file from URL to local path."""
    if filename is None:
        filename = Path(urlparse(url).path).name or "downloaded_file"

    output_path = output_dir / filename
    urllib.request.urlretrieve(url, output_path)
    return output_path


def resolve_presentation(source: str, temp_dir: Path) -> Path:
    """Resolve presentation source to local path, downloading if URL."""
    if is_url(source):
        return download_file(source, temp_dir, "presentation.md")
    return Path(source)


def resolve_theme(theme: str | None, temp_dir: Path) -> str | None:
    """Resolve theme to path or URL suitable for Marp CLI.

    Marp CLI can accept:
    - Local CSS file path
    - HTTP(S) URL directly (it handles the download)
    - Built-in theme names (default, gaia, uncover)
    """
    if theme is None:
        return None

    # Check for aliases first
    if theme.lower() in THEME_ALIASES:
        theme = THEME_ALIASES[theme.lower()]

    if is_url(theme):
        return theme
    return str(Path(theme).absolute())


def render_to_html(
    md_source: str,
    output_dir: Path,
    theme: str | None = None,
) -> Path:
    """Render Marp markdown to HTML for Playwright recording.

    Args:
        md_source: Path or URL to the .md presentation file
        output_dir: Directory for output HTML
        theme: Optional path, URL, or alias to CSS theme
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="marp_"))

    try:
        md_path = resolve_presentation(md_source, temp_dir)
        output = output_dir / f"{md_path.stem}.html"
        cmd = _build_marp_command(md_path, output, theme, temp_dir)

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Marp render failed: {result.stderr}")

        return output

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def _build_marp_command(
    md_path: Path,
    output: Path,
    theme: str | None,
    temp_dir: Path,
) -> list[str]:
    """Build the marp CLI command."""
    cmd = ["marp", "--html", str(md_path), "-o", str(output)]

    resolved_theme = resolve_theme(theme, temp_dir)
    if resolved_theme:
        cmd.extend(["--theme", resolved_theme])

    return cmd


def get_slide_count(html_path: Path) -> int:
    """Count slides in rendered Marp HTML."""
    content = html_path.read_text()
    return content.count("<section ")
