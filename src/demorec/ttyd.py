"""ttyd process management for terminal recording.

Provides utilities for finding, starting, and stopping ttyd processes
used by both recording and preview modes.
"""

import os
import shutil
import socket
import subprocess
from pathlib import Path


def find_free_port() -> int:
    """Find an available port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def check_ttyd() -> bool:
    """Check if ttyd is available."""
    try:
        result = subprocess.run(["ttyd", "--version"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def find_ttyd() -> str:
    """Find ttyd executable, checking common locations.

    Raises:
        RuntimeError: If ttyd is not found
    """
    local_bin = str(Path.home() / ".local/bin")
    search_path = f"{local_bin}:{os.environ.get('PATH', '')}"

    ttyd_path = shutil.which("ttyd", path=search_path)
    if ttyd_path:
        return ttyd_path

    for path in ["/usr/local/bin/ttyd", f"{local_bin}/ttyd"]:
        if Path(path).exists():
            return path

    raise RuntimeError(
        "ttyd not found. Install with:\n"
        "  wget -qO /tmp/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64\n"
        "  chmod +x /tmp/ttyd && sudo mv /tmp/ttyd /usr/local/bin/ttyd"
    )


def make_clean_env() -> dict[str, str]:
    """Create clean environment for ttyd subprocess.

    Removes prompt-related variables that interfere with recording.
    """
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["PS1"] = "$ "
    env["PROMPT_COMMAND"] = ""

    local_bin = str(Path.home() / ".local/bin")
    current_path = env.get("PATH", "")
    if local_bin not in current_path:
        env["PATH"] = f"{local_bin}:{current_path}"

    for key in list(env.keys()):
        if "PROMPT" in key and key != "PROMPT_COMMAND":
            del env[key]

    return env


def start_ttyd(
    port: int,
    env: dict[str, str] | None = None,
    ttyd_path: str | None = None,
) -> subprocess.Popen:
    """Start ttyd subprocess.

    Args:
        port: Port to listen on
        env: Environment variables (uses make_clean_env() if None)
        ttyd_path: Path to ttyd binary (auto-detected if None)

    Returns:
        The subprocess.Popen object
    """
    if ttyd_path is None:
        ttyd_path = find_ttyd()
    if env is None:
        env = make_clean_env()

    cmd = [
        ttyd_path,
        "-p",
        str(port),
        "--writable",
        "--once",
        "/bin/bash",
        "--norc",
        "--noprofile",
    ]
    return subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_ttyd(process: subprocess.Popen | None) -> None:
    """Stop ttyd subprocess gracefully."""
    if not process:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
