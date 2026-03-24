"""Stage directions calculator for vim-based terminal recordings.

Calculates optimal vim commands for scrolling and highlighting code blocks
based on terminal dimensions and desired line ranges.

Also re-exports checkpoint functionality from .checkpoints for a unified API.
"""

import json
from dataclasses import dataclass

# Re-export checkpoint functionality for unified API
from .checkpoints import (
    Checkpoint,
    detect_checkpoints,
    format_checkpoints_json,
    format_checkpoints_text,
)


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
    """Calculate visible line range after scrolling. Returns (first, last) tuple."""
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
    overhead: int = 2,
) -> list[StageDirection]:
    """Calculate stage directions for highlighting blocks."""
    visible_rows = rows - overhead
    directions = []
    current_view = (1, visible_rows)

    for block in highlights:
        direction, current_view = _direction_for_block(block, current_view, visible_rows)
        directions.append(direction)

    return directions


def _direction_for_block(
    block: Block, current_view: tuple[int, int], visible_rows: int
) -> tuple[StageDirection, tuple[int, int]]:
    """Calculate direction for a single block."""
    view_start, view_end = current_view
    block_visible = block.start >= view_start and block.end <= view_end

    if block_visible:
        return _no_scroll_direction(block, current_view), current_view

    return _scroll_direction(block, visible_rows)


def _no_scroll_direction(block: Block, visible_range: tuple[int, int]) -> StageDirection:
    """Create direction when block is already visible."""
    return StageDirection(
        block=block,
        needs_scroll=False,
        scroll_to=None,
        scroll_method=None,
        visible_range=visible_range,
        commands=[f"{block.start}GV{block.end}G"],
        notes=["Visible in current view"],
    )


def _scroll_direction(  # length-ok
    block: Block, visible_rows: int
) -> tuple[StageDirection, tuple[int, int]]:
    """Create direction when scrolling is needed."""
    scroll_to, method, notes = _determine_scroll(block, visible_rows)
    new_view = calculate_visible_range(scroll_to, visible_rows, method)
    cmds = [f"{scroll_to}G{method}", f"{block.start}GV{block.end}G"]
    direction = StageDirection(
        block=block,
        needs_scroll=True,
        scroll_to=scroll_to,
        scroll_method=method,
        visible_range=new_view,
        commands=cmds,
        notes=notes,
    )
    return direction, new_view


def _determine_scroll(block: Block, visible_rows: int) -> tuple[int, str, list[str]]:
    """Determine scroll target and method."""
    # Try centering first
    view = calculate_visible_range(block.middle, visible_rows, "zz")
    if block.start >= view[0] and block.end <= view[1]:
        return block.middle, "zz", ["Scroll to center block"]
    # Fall back to top alignment
    return block.start, "zt", ["Block larger than view, showing from top"]


def format_directions_text(directions: list[StageDirection], rows: int) -> str:
    """Format stage directions as human-readable text."""
    lines = [f"Stage Directions for {rows}-row terminal:", ""]
    for i, d in enumerate(directions, 1):
        lines.extend(_format_direction_text(i, d))
    return "\n".join(lines)


def _format_direction_text(index: int, d: StageDirection) -> list[str]:
    """Format a single direction as text lines."""
    lines = [f"Block {index}: lines {d.block.start}-{d.block.end} ({d.block.size} lines)"]
    vis_start, vis_end = d.visible_range

    if d.needs_scroll:
        scroll_cmd = f"{d.scroll_to}G{d.scroll_method}"
        lines.append(f"  Scroll: {scroll_cmd} → shows lines {vis_start}-{vis_end}")
    else:
        lines.append(f"  Position: visible in current view (lines {vis_start}-{vis_end})")

    lines.append("  Commands:")
    lines.extend(f'    Type "{cmd}"' for cmd in d.commands)
    lines.extend(f"  Note: {note}" for note in (d.notes or []))
    lines.append("")
    return lines


def format_directions_json(directions: list[StageDirection], rows: int) -> str:
    """Format stage directions as JSON."""
    data = {
        "terminal_rows": rows,
        "visible_rows": rows - 2,
        "blocks": [_direction_to_dict(d) for d in directions],
    }
    return json.dumps(data, indent=2)


def _direction_to_dict(d: StageDirection) -> dict:
    """Convert a StageDirection to a dictionary."""
    block_data = {
        "lines": [d.block.start, d.block.end],
        "size": d.block.size,
        "needs_scroll": d.needs_scroll,
        "visible_range": list(d.visible_range),
        "commands": d.commands,
    }
    if d.needs_scroll:
        block_data.update({"scroll_to": d.scroll_to, "scroll_method": d.scroll_method})
    if d.notes:
        block_data["notes"] = d.notes
    return block_data


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


__all__ = [
    # Stage directions
    "Block",
    "StageDirection",
    "parse_highlights",
    "calculate_visible_range",
    "calculate_stage_directions",
    "format_directions_text",
    "format_directions_json",
    "format_directions_demorec",
    # Checkpoints (re-exported)
    "Checkpoint",
    "detect_checkpoints",
    "format_checkpoints_text",
    "format_checkpoints_json",
]
