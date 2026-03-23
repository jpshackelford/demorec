"""Checkpoint detection and formatting for demorec scripts.

Checkpoints are automatically detected locations in a script where
the visual state should be verified (e.g., after visual selections).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Checkpoint:
    """An automatically detected checkpoint in a script."""

    line_number: int  # Line in script file
    command_index: int  # Index in command list
    event_type: str  # Type of event that triggered checkpoint
    description: str  # Human-readable description
    expected_highlight: tuple[int, int] | None = None  # Expected line range


def _parse_type_command(line: str) -> str | None:
    """Extract content from a Type command."""
    match = re.match(r'Type\s+"([^"]+)"', line)
    return match.group(1) if match else None


def _parse_goto(typed_content: str) -> int | None:
    """Parse goto line command (e.g., '6G', '27G')."""
    match = re.match(r"(\d+)G", typed_content)
    return int(match.group(1)) if match else None


def _is_visual_mode_start(typed_content: str) -> bool:
    """Check if typed content starts visual mode."""
    return typed_content in ("V", "v")


def _should_skip_line(line: str) -> bool:
    """Check if line should be skipped for command counting."""
    if not line:
        return True
    if line.startswith("@"):
        return True
    if line.startswith("Set ") or line.startswith("Output "):
        return True
    return False


def detect_checkpoints(script_path: Path) -> list[Checkpoint]:
    """Detect natural checkpoint locations in a .demorec script.

    Checkpoints are detected at:
    1. End of visual selections (V...G pattern before Escape)
    2. After narration points (@narrate:after)
    """
    with open(script_path) as f:
        lines = f.readlines()

    checkpoints = []
    state = _CheckpointDetectorState()

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        line_num = i + 1

        if line_stripped.startswith("#"):
            _handle_comment(line_stripped, line_num, state, checkpoints)
            continue

        if _should_skip_line(line_stripped):
            continue

        _process_command_line(line_stripped, line_num, state, checkpoints)

    return checkpoints


class _CheckpointDetectorState:
    """State for checkpoint detection."""

    def __init__(self):
        self.command_index = 0
        self.in_visual_mode = False
        self.visual_start_line: int | None = None
        self.pending_goto: int | None = None
        self.last_type_line = 0


def _handle_comment(line: str, line_num: int, state: _CheckpointDetectorState, checkpoints: list):
    """Handle comment line, checking for narration markers."""
    if "@narrate:after" not in line:
        return

    expected = (state.visual_start_line, state.pending_goto) if state.visual_start_line else None
    checkpoints.append(
        Checkpoint(
            line_number=line_num,
            command_index=state.command_index,
            event_type="narration",
            description="Narration point - content should be visible",
            expected_highlight=expected,
        )
    )


def _process_command_line(
    line: str, line_num: int, state: _CheckpointDetectorState, checkpoints: list
):
    """Process a command line for checkpoint detection."""
    typed_content = _parse_type_command(line)

    if typed_content:
        _handle_type_command(typed_content, line_num, state)
    elif line == "Escape":
        _handle_escape(line_num, state, checkpoints)
    elif line in ("Enter",) or line.startswith("Sleep"):
        state.command_index += 1


def _handle_type_command(typed_content: str, line_num: int, state: _CheckpointDetectorState):
    """Handle a Type command."""
    state.last_type_line = line_num

    goto_line = _parse_goto(typed_content)
    if goto_line:
        state.pending_goto = goto_line

    if _is_visual_mode_start(typed_content):
        state.in_visual_mode = True
        state.visual_start_line = state.pending_goto

    state.command_index += 1


def _handle_escape(line_num: int, state: _CheckpointDetectorState, checkpoints: list):
    """Handle Escape command - may end visual selection."""
    if state.in_visual_mode and state.visual_start_line and state.pending_goto:
        start = min(state.visual_start_line, state.pending_goto)
        end = max(state.visual_start_line, state.pending_goto)
        checkpoints.append(
            Checkpoint(
                line_number=state.last_type_line,
                command_index=state.command_index - 1,
                event_type="visual_selection",
                description=f"Visual selection complete: lines {start}-{end}",
                expected_highlight=(start, end),
            )
        )

    state.in_visual_mode = False
    state.visual_start_line = None
    state.command_index += 1


def format_checkpoints_text(checkpoints: list[Checkpoint]) -> str:
    """Format detected checkpoints as human-readable text."""
    if not checkpoints:
        return "No checkpoints detected."

    lines = [f"Detected {len(checkpoints)} checkpoints:", ""]

    for i, cp in enumerate(checkpoints, 1):
        lines.append(f"Checkpoint {i} (line {cp.line_number}):")
        lines.append(f"  Event: {cp.event_type}")
        lines.append(f"  Description: {cp.description}")
        if cp.expected_highlight:
            hl_start, hl_end = cp.expected_highlight
            lines.append(f"  Expected visible: lines {hl_start}-{hl_end}")
        lines.append("")

    return "\n".join(lines)


def format_checkpoints_json(checkpoints: list[Checkpoint]) -> str:
    """Format detected checkpoints as JSON."""
    data = {
        "checkpoint_count": len(checkpoints),
        "checkpoints": [
            {
                "line_number": cp.line_number,
                "command_index": cp.command_index,
                "event_type": cp.event_type,
                "description": cp.description,
                "expected_highlight": list(cp.expected_highlight)
                if cp.expected_highlight
                else None,
            }
            for cp in checkpoints
        ],
    }
    return json.dumps(data, indent=2)
