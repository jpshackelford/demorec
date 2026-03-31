"""Marp CLI integration for rendering presentations."""

import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

THEME_ALIASES = {
    "openhands": "https://raw.githubusercontent.com/jpshackelford/marp-intro/main/openhands-theme/openhands.css",
}

# Security limits for downloads
DOWNLOAD_TIMEOUT_SECONDS = 30
DOWNLOAD_MAX_SIZE_BYTES = 100_000_000  # 100MB


def check_marp_installed() -> bool:
    """Check if marp CLI is available."""
    return shutil.which("marp") is not None


def is_url(path: str) -> bool:
    """Check if a path is an HTTP(S) URL."""
    return path.startswith(("http://", "https://"))


def _check_content_length(response) -> None:
    """Validate response Content-Length is within limits."""
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > DOWNLOAD_MAX_SIZE_BYTES:
        raise ValueError(f"File too large: {content_length} bytes (max {DOWNLOAD_MAX_SIZE_BYTES})")


def download_file(url: str, output_dir: Path, filename: str | None = None) -> Path:
    """Download a file from URL to local path with security limits."""
    if filename is None:
        filename = Path(urlparse(url).path).name or "downloaded_file"
    output_path = output_dir / filename
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            _check_content_length(response)
            output_path.write_bytes(response.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to download {url}: {e}") from e
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


def _validate_path_arg(path: str, name: str):
    """Validate a path argument doesn't contain suspicious characters.

    Args:
        path: The path string to validate
        name: Human-readable name for error messages

    Raises:
        ValueError: If path contains null bytes or is empty/whitespace
    """
    if "\x00" in path:
        raise ValueError(f"{name} contains null bytes")
    if not path or path.isspace():
        raise ValueError(f"{name} is empty or whitespace")


def _build_marp_command(
    md_path: Path,
    output: Path,
    theme: str | None,
    temp_dir: Path,
) -> list[str]:
    """Build the marp CLI command with validated arguments."""
    md_str = str(md_path)
    output_str = str(output)

    _validate_path_arg(md_str, "Presentation path")
    _validate_path_arg(output_str, "Output path")

    cmd = ["marp", "--html", md_str, "-o", output_str]

    resolved_theme = resolve_theme(theme, temp_dir)
    if resolved_theme:
        _validate_path_arg(resolved_theme, "Theme path")
        cmd.extend(["--theme", resolved_theme])

    return cmd


def get_slide_count(html_path: Path) -> int:
    """Count slides in rendered Marp HTML."""
    content = html_path.read_text()
    return content.count("<section ")
