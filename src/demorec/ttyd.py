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
    """Find ttyd executable, checking common locations."""
    path = _search_ttyd_path()
    if path:
        return path
    raise RuntimeError(_ttyd_not_found_msg())


def _search_ttyd_path() -> str | None:
    """Search for ttyd in PATH and common locations."""
    local_bin = str(Path.home() / ".local/bin")
    search_path = f"{local_bin}:{os.environ.get('PATH', '')}"
    path = shutil.which("ttyd", path=search_path)
    if path:
        return path
    for p in ["/usr/local/bin/ttyd", f"{local_bin}/ttyd"]:
        if Path(p).exists():
            return p
    return None


def _ttyd_not_found_msg() -> str:
    """Return error message for missing ttyd."""
    return (
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
    session_name: str | None = None,
) -> subprocess.Popen:
    """Start ttyd subprocess.

    Args:
        port: Port to listen on
        env: Environment variables (default: clean env)
        ttyd_path: Path to ttyd binary (default: auto-detect)
        session_name: If provided, use tmux for persistent sessions
    """
    ttyd_path = ttyd_path or find_ttyd()
    env = env or make_clean_env()
    cmd = _build_ttyd_cmd(ttyd_path, port, session_name)
    return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _build_ttyd_cmd(ttyd_path: str, port: int, session_name: str | None = None) -> list[str]:
    """Build ttyd command line."""
    base = [ttyd_path, "-p", str(port), "--writable"]
    if session_name:
        # Use tmux for persistent sessions - attach to existing session
        # The session should be pre-created by ensure_tmux_session()
        return base + ["tmux", "attach-session", "-t", f"demorec-{session_name}"]
    # Non-persistent: use --once for clean exit
    return base + ["--once", "/bin/bash", "--norc", "--noprofile"]


def _tmux_session_exists(tmux_session: str) -> bool:
    """Check if a tmux session exists."""
    result = subprocess.run(["tmux", "has-session", "-t", tmux_session], capture_output=True)
    return result.returncode == 0


def _create_tmux_session(tmux_session: str) -> None:  # length-ok: subprocess calls
    """Create a new tmux session with clean shell environment."""
    env = make_clean_env()

    env_args = ["PS1=$ "]
    for key in ["LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"]:
        if key in env:
            env_args.append(f"{key}={env[key]}")

    cmd = [
        "tmux",
        "new-session",
        "-d",
        "-s",
        tmux_session,
        "/usr/bin/env",
        *env_args,
        "/bin/bash",
        "--norc",
        "--noprofile",
    ]
    subprocess.run(cmd, env=env, capture_output=True)
    subprocess.run(["tmux", "set-option", "-t", tmux_session, "status", "off"], capture_output=True)


def ensure_tmux_session(session_name: str) -> None:
    """Ensure a tmux session exists, creating it if needed."""
    tmux_session = f"demorec-{session_name}"
    if not _tmux_session_exists(tmux_session):
        _create_tmux_session(tmux_session)


def stop_ttyd(process: subprocess.Popen | None) -> None:
    """Stop ttyd subprocess gracefully."""
    if not process:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
