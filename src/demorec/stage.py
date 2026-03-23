"""Stage directions calculator for vim-based terminal recordings.

Calculates optimal vim commands for scrolling and highlighting code blocks
based on terminal dimensions and desired line ranges.
"""

import json
from dataclasses import dataclass


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


def _scroll_direction(block: Block, visible_rows: int) -> tuple[StageDirection, tuple[int, int]]:
    """Create direction when scrolling is needed."""
    scroll_to = block.middle
    scroll_method = "zz"
    new_view = calculate_visible_range(scroll_to, visible_rows, scroll_method)

    # Check if block fits after scroll
    if not (block.start >= new_view[0] and block.end <= new_view[1]):
        scroll_to = block.start
        scroll_method = "zt"
        new_view = calculate_visible_range(scroll_to, visible_rows, scroll_method)
        notes = ["Block larger than view, showing from top"]
    else:
        notes = ["Scroll to center block"]

    direction = StageDirection(
        block=block,
        needs_scroll=True,
        scroll_to=scroll_to,
        scroll_method=scroll_method,
        visible_range=new_view,
        commands=[f"{scroll_to}G{scroll_method}", f"{block.start}GV{block.end}G"],
        notes=notes,
    )
    return direction, new_view


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
            lines.append(f"  Position: visible in current view (lines {vis_start}-{vis_end})")

        lines.append("  Commands:")
        for cmd in d.commands:
            lines.append(f'    Type "{cmd}"')

        if d.notes:
            for note in d.notes:
                lines.append(f"  Note: {note}")

        lines.append("")

    return "\n".join(lines)


def format_directions_json(directions: list[StageDirection], rows: int) -> str:
    """Format stage directions as JSON."""
    data = {"terminal_rows": rows, "visible_rows": rows - 2, "blocks": []}

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


# Re-export checkpoint functionality for backwards compatibility
from .checkpoints import (  # noqa: E402, F401
    Checkpoint,
    detect_checkpoints,
    format_checkpoints_json,
    format_checkpoints_text,
)

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
