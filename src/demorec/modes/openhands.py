"""High-level OpenHands CLI primitives for demo recording.

Provides Install, Start, Prompt, MultilinePrompt, Command, Palette, and Quit
commands that handle all the OpenHands CLI complexity internally, including:
- Installing the CLI via uv
- Launching and waiting for the CLI to be ready
- Sending single-line and multi-line prompts
- Executing slash commands
- Clean exit

Preflight checks ensure the CLI is installed and LLM is configured.

Example usage in .demorec:
    @mode terminal:openhands

    Install
    Start
    Prompt "Tell me a dad joke"
    MultilinePrompt "Create a Python function that:
    - Takes a list of numbers
    - Returns only the even ones"
    Command "/history"
    Quit
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OpenHandsState:
    """Tracks OpenHands CLI session state."""

    running: bool = False


def check_openhands_installed() -> bool:
    """Check if openhands CLI is available on the system."""
    if shutil.which("openhands"):
        return True
    local_bin = Path.home() / ".local" / "bin" / "openhands"
    return local_bin.exists()


def check_llm_configured() -> bool:
    """Check if LLM is configured for OpenHands CLI."""
    settings_file = Path.home() / ".openhands" / "agent_settings.json"
    return settings_file.exists()


def preflight_check() -> list[str]:
    """Run preflight checks for OpenHands CLI primitives.

    Returns list of error messages (empty if all checks pass).
    Called before recording begins to ensure dependencies are ready.

    Note: If Install command is used, CLI installation is not required.
    LLM configuration is required unless using --override-with-envs flag.
    """
    errors = []

    # Check if LLM is configured via settings file OR environment variables
    # LLM_MODEL and LLM_API_KEY are required; LLM_BASE_URL is optional (defaults to OpenAI)
    has_env_config = all(os.environ.get(v) for v in ("LLM_MODEL", "LLM_API_KEY"))
    has_settings_config = check_llm_configured()

    if not has_env_config and not has_settings_config:
        errors.append(
            "OpenHands LLM not configured. Please configure LLM settings:\n"
            "  1. Run 'openhands' to go through first-time setup, or\n"
            "  2. Set LLM_MODEL and LLM_API_KEY environment variables\n"
            "     (LLM_BASE_URL is optional), and use --override-with-envs flag"
        )

    return errors


def generate_install_commands(version: str | None = None) -> list[tuple[str, float]]:
    """Generate commands to install OpenHands CLI via uv.

    Args:
        version: Optional specific version to install (e.g., "1.14.0")

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    if version:
        cmd = f"uv tool install openhands=={version} --python 3.12"
    else:
        cmd = "uv tool install openhands --python 3.12"

    return [
        (cmd, 0),
        ("ENTER", 30.0),  # Wait for installation
        ('export PATH="$HOME/.local/bin:$PATH"', 0),
        ("ENTER", 0.5),
    ]


def generate_start_commands(state: OpenHandsState) -> list[tuple[str, float]]:
    """Generate commands to start OpenHands CLI.

    Args:
        state: OpenHandsState to update

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    state.running = True

    return [
        ("openhands", 0),
        ("ENTER", 5.0),  # Wait for CLI to initialize
    ]


def generate_prompt_commands(text: str, wait: float = 10.0) -> list[tuple[str, float]]:
    """Generate commands to send a single-line prompt.

    Args:
        text: The prompt text to send
        wait: Seconds to wait for response (default 10s)

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    return [
        (text, 0.02),  # Type the prompt
        ("ENTER", wait),  # Submit and wait
    ]


def generate_multiline_commands(text: str, wait: float = 15.0) -> list[tuple[str, float]]:
    """Generate commands for multi-line prompt input.

    Args:
        text: Multi-line prompt text (lines separated by newlines)
        wait: Seconds to wait for response (default 15s)

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    commands = []

    # Enter multiline mode with CTRL+L
    commands.append(("CTRL+L", 0.3))

    # Type each line with Enter for newlines
    lines = text.strip().split("\n")
    for i, line in enumerate(lines):
        commands.append((line, 0.02))
        if i < len(lines) - 1:  # Don't add Enter after last line
            commands.append(("ENTER", 0.1))

    # Submit with Ctrl+J (exits multiline mode automatically)
    commands.append(("CTRL+J", wait))

    return commands


def generate_command_commands(slash_cmd: str) -> list[tuple[str, float]]:
    """Generate commands to execute a slash command.

    Args:
        slash_cmd: The slash command (e.g., "/history", "/help")

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    return [
        (slash_cmd, 0.02),
        ("ENTER", 1.0),
    ]


def generate_palette_commands() -> list[tuple[str, float]]:
    """Generate commands to open the command palette.

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    return [("CTRL+P", 0.5)]


def generate_quit_commands(state: OpenHandsState) -> list[tuple[str, float]]:
    """Generate commands to quit OpenHands CLI.

    Args:
        state: OpenHandsState to update

    Returns:
        List of (keys_to_type, delay_after) tuples
    """
    state.running = False

    return [("CTRL+Q", 1.0)]


class OpenHandsCommandExpander:
    """Expands high-level OpenHands commands into low-level terminal commands.

    This class is used by the terminal recorder to expand Install, Start,
    Prompt, etc. commands into the actual keystrokes needed.

    State validation ensures commands are used in valid sequence:
    - Start must be called before Prompt, MultilinePrompt, Command, Palette, or Quit
    - Start cannot be called twice without Quit in between
    - Quit cannot be called when CLI is not running
    """

    COMMANDS = ("Install", "Start", "Prompt", "MultilinePrompt", "Command", "Palette", "Quit")
    # Commands that require the CLI to be running
    _REQUIRES_RUNNING = ("Prompt", "MultilinePrompt", "Command", "Palette", "Quit")

    def __init__(self):
        self.state = OpenHandsState()
        self._handlers = {
            "Install": self._expand_install,
            "Start": self._expand_start,
            "Prompt": self._expand_prompt,
            "MultilinePrompt": self._expand_multiline,
            "Command": self._expand_command,
            "Palette": self._expand_palette,
            "Quit": self._expand_quit,
        }

    def expand_command(self, cmd_name: str, cmd_args: list[str]) -> list[tuple[str, float]]:
        """Expand a high-level command into keystrokes.

        Raises:
            ValueError: If command is used in invalid state (e.g., Prompt before Start)
        """
        handler = self._handlers.get(cmd_name)
        return handler(cmd_args) if handler else []

    def _require_running(self, cmd_name: str) -> None:
        """Raise ValueError if CLI is not running."""
        if not self.state.running:
            raise ValueError(
                f"Cannot use '{cmd_name}' before 'Start'. "
                f"The OpenHands CLI must be started first."
            )

    def _expand_install(self, args: list[str]) -> list[tuple[str, float]]:
        version = args[0] if args else None
        return generate_install_commands(version)

    def _expand_start(self, args: list[str]) -> list[tuple[str, float]]:
        if self.state.running:
            raise ValueError(
                "Cannot use 'Start' when CLI is already running. "
                "Use 'Quit' first to stop the current session."
            )
        return generate_start_commands(self.state)

    def _expand_prompt(self, args: list[str]) -> list[tuple[str, float]]:
        self._require_running("Prompt")
        if not args:
            return []
        text = args[0]
        wait = float(args[1]) if len(args) > 1 else 10.0
        return generate_prompt_commands(text, wait)

    def _expand_multiline(self, args: list[str]) -> list[tuple[str, float]]:
        self._require_running("MultilinePrompt")
        if not args:
            return []
        text = args[0]
        wait = float(args[1]) if len(args) > 1 else 15.0
        return generate_multiline_commands(text, wait)

    def _expand_command(self, args: list[str]) -> list[tuple[str, float]]:
        self._require_running("Command")
        if not args:
            return []
        return generate_command_commands(args[0])

    def _expand_palette(self, args: list[str]) -> list[tuple[str, float]]:
        self._require_running("Palette")
        return generate_palette_commands()

    def _expand_quit(self, args: list[str]) -> list[tuple[str, float]]:
        self._require_running("Quit")
        return generate_quit_commands(self.state)

    def is_openhands_command(self, cmd_name: str) -> bool:
        """Check if a command is a high-level OpenHands command."""
        return cmd_name in self.COMMANDS
