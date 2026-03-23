"""Stage directions calculator for vim-based terminal recordings.

Calculates optimal vim commands for scrolling and highlighting code blocks
based on terminal dimensions and desired line ranges.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Block:
    """A block of lines to highlight."""
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start + 1

    @property
    def middle(self) -> int:
        return (self.start + self.end) // 2


@dataclass
class StageDirection:
    """Stage direction for a single block."""
    block: Block
    needs_scroll: bool
    scroll_to: int | None
    scroll_method: str | None  # "zz" (center), "zt" (top), "zb" (bottom)
    visible_range: tuple[int, int]  # Lines visible after scroll
    commands: list[str]
    notes: list[str]


def parse_highlights(highlights_str: str) -> list[Block]:
    """Parse highlight string like '6-7,11-16,26-34' into Block objects."""
    blocks = []
    for part in highlights_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            blocks.append(Block(int(start), int(end)))
        else:
            # Single line
            line = int(part)
            blocks.append(Block(line, line))
    return blocks


def calculate_visible_range(
    scroll_line: int, visible_rows: int, scroll_method: str = "zz"
) -> tuple[int, int]:
    """Calculate which lines are visible after scrolling.

    Args:
        scroll_line: The line we're scrolling to
        visible_rows: Number of visible rows in terminal
        scroll_method: "zz" (center), "zt" (top), "zb" (bottom)

    Returns:
        (first_visible, last_visible) tuple
    """
    if scroll_method == "zt":
        # Line at top
        first = scroll_line
        last = scroll_line + visible_rows - 1
    elif scroll_method == "zb":
        # Line at bottom
        first = scroll_line - visible_rows + 1
        last = scroll_line
    else:  # zz - center
        half = visible_rows // 2
        first = scroll_line - half
        last = scroll_line + (visible_rows - half - 1)

    # Clamp to valid line numbers (minimum 1)
    first = max(1, first)
    return (first, last)


def calculate_stage_directions(
    rows: int,
    highlights: list[Block],
    overhead: int = 2  # Lines used by prompt/status bar
) -> list[StageDirection]:
    """Calculate stage directions for highlighting blocks.

    Args:
        rows: Terminal rows
        highlights: List of Block objects to highlight
        overhead: Lines used by vim status bar, etc.

    Returns:
        List of StageDirection objects
    """
    visible_rows = rows - overhead
    directions = []

    # Track current view position (start with initial view)
    current_view_start = 1
    current_view_end = visible_rows

    for block in highlights:
        notes = []

        # Check if block is fully visible in current view
        block_visible = (block.start >= current_view_start and
                        block.end <= current_view_end)

        if block_visible:
            # No scroll needed
            directions.append(StageDirection(
                block=block,
                needs_scroll=False,
                scroll_to=None,
                scroll_method=None,
                visible_range=(current_view_start, current_view_end),
                commands=[f"{block.start}GV{block.end}G"],
                notes=["Visible in current view"]
            ))
        else:
            # Need to scroll - center on middle of block
            scroll_to = block.middle
            scroll_method = "zz"

            # Calculate new visible range
            new_view = calculate_visible_range(scroll_to, visible_rows, scroll_method)

            # Check if block fits after scroll
            block_fits = (block.start >= new_view[0] and block.end <= new_view[1])

            if not block_fits:
                # Block is larger than visible area, use top alignment
                scroll_to = block.start
                scroll_method = "zt"
                new_view = calculate_visible_range(scroll_to, visible_rows, scroll_method)
                notes.append("Block larger than view, showing from top")

            # Build commands
            commands = [
                f"{scroll_to}G{scroll_method}",
                f"{block.start}GV{block.end}G"
            ]

            directions.append(StageDirection(
                block=block,
                needs_scroll=True,
                scroll_to=scroll_to,
                scroll_method=scroll_method,
                visible_range=new_view,
                commands=commands,
                notes=notes if notes else ["Scroll to center block"]
            ))

            # Update current view
            current_view_start, current_view_end = new_view

    return directions


def format_directions_text(directions: list[StageDirection], rows: int) -> str:
    """Format stage directions as human-readable text."""
    lines = [f"Stage Directions for {rows}-row terminal:", ""]

    for i, d in enumerate(directions, 1):
        lines.append(f"Block {i}: lines {d.block.start}-{d.block.end} ({d.block.size} lines)")

        if d.needs_scroll:
            vis_start, vis_end = d.visible_range
            lines.append(
                f"  Scroll: {d.scroll_to}G{d.scroll_method} → shows lines {vis_start}-{vis_end}"
            )
        else:
            vis_start, vis_end = d.visible_range
            lines.append(
                f"  Position: visible in current view (lines {vis_start}-{vis_end})"
            )

        lines.append("  Commands:")
        for cmd in d.commands:
            lines.append(f"    Type \"{cmd}\"")

        if d.notes:
            for note in d.notes:
                lines.append(f"  Note: {note}")

        lines.append("")

    return "\n".join(lines)


def format_directions_json(directions: list[StageDirection], rows: int) -> str:
    """Format stage directions as JSON."""
    data = {
        "terminal_rows": rows,
        "visible_rows": rows - 2,
        "blocks": []
    }

    for d in directions:
        block_data = {
            "lines": [d.block.start, d.block.end],
            "size": d.block.size,
            "needs_scroll": d.needs_scroll,
            "visible_range": list(d.visible_range),
            "commands": d.commands,
        }
        if d.needs_scroll:
            block_data["scroll_to"] = d.scroll_to
            block_data["scroll_method"] = d.scroll_method
        if d.notes:
            block_data["notes"] = d.notes

        data["blocks"].append(block_data)

    return json.dumps(data, indent=2)


def format_directions_demorec(directions: list[StageDirection]) -> str:
    """Format stage directions as .demorec script snippets."""
    lines = ["# Generated stage directions", ""]

    for i, d in enumerate(directions, 1):
        lines.append(f"# Block {i}: lines {d.block.start}-{d.block.end}")

        if i > 1:
            lines.append("Escape")
            lines.append("Sleep 0.3s")

        for cmd in d.commands:
            # Split scroll and highlight into separate commands
            lines.append(f'Type "{cmd}"')
            lines.append("Sleep 0.3s")

        lines.append("Sleep 1s")
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# Checkpoint Detection
# =============================================================================

@dataclass
class Checkpoint:
    """An automatically detected checkpoint in a script."""
    line_number: int          # Line in script file
    command_index: int        # Index in command list
    event_type: str           # Type of event that triggered checkpoint
    description: str          # Human-readable description
    expected_highlight: tuple[int, int] | None = None  # Expected line range if visual selection


def detect_checkpoints(script_path: Path) -> list[Checkpoint]:
    """Detect natural checkpoint locations in a .demorec script.

    Checkpoints are detected at:
    1. End of visual selections (V...G pattern before Escape or next action)
    2. After narration points (@narrate:after)
    3. After file opens (vim/less + Enter + Sleep)
    4. After scroll positioning (Gzz/zt/zb + Sleep)
    """
    with open(script_path) as f:
        lines = f.readlines()

    checkpoints = []
    command_index = 0

    # State tracking
    in_visual_mode = False
    visual_start_line: int | None = None
    pending_goto: int | None = None
    last_type_line = 0

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        line_num = i + 1  # 1-indexed

        # Skip comments and empty lines for command counting
        # but check for narration markers
        if line_stripped.startswith("#"):
            if "@narrate:after" in line_stripped:
                # Narration point - the previous visual selection should be visible
                expected = (visual_start_line, pending_goto) if visual_start_line else None
                checkpoints.append(Checkpoint(
                    line_number=line_num,
                    command_index=command_index,
                    event_type="narration",
                    description="Narration point - content should be visible",
                    expected_highlight=expected
                ))
            continue

        is_directive = line_stripped.startswith("@")
        is_setting = line_stripped.startswith("Set ") or line_stripped.startswith("Output ")
        if not line_stripped or is_directive or is_setting:
            continue

        # Parse Type commands
        type_match = re.match(r'Type\s+"([^"]+)"', line_stripped)
        if type_match:
            typed_content = type_match.group(1)
            last_type_line = line_num

            # Detect goto line commands (e.g., "6G", "27G")
            goto_match = re.match(r'(\d+)G', typed_content)
            if goto_match:
                pending_goto = int(goto_match.group(1))

            # Detect visual mode start
            if typed_content == "V" or typed_content == "v":
                in_visual_mode = True
                visual_start_line = pending_goto

            # Detect scroll commands
            if typed_content in ("zz", "zt", "zb"):
                # Scroll positioning
                pass

            command_index += 1

        # Detect Escape - end of visual mode
        elif line_stripped == "Escape":
            if in_visual_mode and visual_start_line and pending_goto:
                # End of visual selection - this is a checkpoint
                start = min(visual_start_line, pending_goto)
                end = max(visual_start_line, pending_goto)
                checkpoints.append(Checkpoint(
                    line_number=last_type_line,  # Use line of last Type command
                    command_index=command_index - 1,
                    event_type="visual_selection",
                    description=f"Visual selection complete: lines {start}-{end}",
                    expected_highlight=(start, end)
                ))

            in_visual_mode = False
            visual_start_line = None
            command_index += 1

        # Enter, Sleep, etc.
        elif line_stripped == "Enter":
            command_index += 1
        elif line_stripped.startswith("Sleep"):
            command_index += 1

    return checkpoints


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
                "expected_highlight": list(cp.expected_highlight) if cp.expected_highlight else None
            }
            for cp in checkpoints
        ]
    }
    return json.dumps(data, indent=2)
