"""Unit tests for stage module.

Tests cover:
- Block dataclass
- StageDirection dataclass
- parse_highlights
- calculate_visible_range
- calculate_stage_directions
- format_directions_text
- format_directions_json
- format_directions_demorec
"""

import json

import pytest

from demorec.stage import (
    Block,
    StageDirection,
    _determine_scroll,
    _direction_for_block,
    _format_direction_text,
    _no_scroll_direction,
    _scroll_direction,
    calculate_stage_directions,
    calculate_visible_range,
    format_directions_demorec,
    format_directions_json,
    format_directions_text,
    parse_highlights,
)


class TestBlock:
    """Test Block dataclass."""

    def test_block_creation(self):
        """Should create block with start and end."""
        block = Block(start=10, end=20)
        assert block.start == 10
        assert block.end == 20

    def test_block_size(self):
        """Should calculate size correctly."""
        block = Block(start=10, end=20)
        assert block.size == 11  # inclusive

    def test_block_size_single_line(self):
        """Should handle single line block."""
        block = Block(start=5, end=5)
        assert block.size == 1

    def test_block_middle(self):
        """Should calculate middle correctly."""
        block = Block(start=10, end=20)
        assert block.middle == 15

    def test_block_middle_single_line(self):
        """Should handle middle for single line."""
        block = Block(start=5, end=5)
        assert block.middle == 5


class TestStageDirection:
    """Test StageDirection dataclass."""

    def test_stage_direction_creation(self):
        """Should create direction with all fields."""
        block = Block(10, 20)
        direction = StageDirection(
            block=block,
            needs_scroll=True,
            scroll_to=15,
            scroll_method="zz",
            visible_range=(5, 25),
            commands=["15Gzz", "10GV20G"],
            notes=["Scroll to center block"],
        )
        assert direction.block == block
        assert direction.needs_scroll is True
        assert direction.scroll_to == 15
        assert direction.scroll_method == "zz"
        assert direction.visible_range == (5, 25)
        assert len(direction.commands) == 2
        assert len(direction.notes) == 1


class TestParseHighlights:
    """Test parse_highlights function."""

    def test_parse_single_range(self):
        """Should parse single range."""
        blocks = parse_highlights("6-7")
        assert len(blocks) == 1
        assert blocks[0].start == 6
        assert blocks[0].end == 7

    def test_parse_multiple_ranges(self):
        """Should parse multiple comma-separated ranges."""
        blocks = parse_highlights("6-7,11-16,26-34")
        assert len(blocks) == 3
        assert blocks[0] == Block(6, 7)
        assert blocks[1] == Block(11, 16)
        assert blocks[2] == Block(26, 34)

    def test_parse_single_line(self):
        """Should parse single line (no dash)."""
        blocks = parse_highlights("15")
        assert len(blocks) == 1
        assert blocks[0].start == 15
        assert blocks[0].end == 15

    def test_parse_mixed_ranges_and_single(self):
        """Should parse mix of ranges and single lines."""
        blocks = parse_highlights("5,10-15,20")
        assert len(blocks) == 3
        assert blocks[0] == Block(5, 5)
        assert blocks[1] == Block(10, 15)
        assert blocks[2] == Block(20, 20)

    def test_parse_with_spaces(self):
        """Should handle whitespace in input."""
        blocks = parse_highlights(" 6-7 , 11-16 ")
        assert len(blocks) == 2
        assert blocks[0] == Block(6, 7)
        assert blocks[1] == Block(11, 16)


class TestCalculateVisibleRange:
    """Test calculate_visible_range function."""

    def test_zz_center(self):
        """Should center line with zz method."""
        first, last = calculate_visible_range(50, 20, "zz")
        # 20 rows centered on 50: half=10, first=40, last=49
        assert first == 40
        assert last == 59

    def test_zt_top(self):
        """Should put line at top with zt method."""
        first, last = calculate_visible_range(10, 20, "zt")
        assert first == 10
        assert last == 29

    def test_zb_bottom(self):
        """Should put line at bottom with zb method."""
        first, last = calculate_visible_range(30, 20, "zb")
        assert first == 11
        assert last == 30

    def test_clamp_to_minimum(self):
        """Should clamp first line to minimum 1."""
        first, last = calculate_visible_range(5, 20, "zz")
        assert first >= 1

    def test_default_is_zz(self):
        """Should default to zz if method not specified."""
        result1 = calculate_visible_range(50, 20)
        result2 = calculate_visible_range(50, 20, "zz")
        assert result1 == result2


class TestDetermineScroll:
    """Test _determine_scroll function."""

    def test_prefer_centering(self):
        """Should prefer centering when block fits."""
        block = Block(15, 17)  # 3 lines
        scroll_to, method, notes = _determine_scroll(block, 20)
        assert method == "zz"
        assert scroll_to == block.middle

    def test_fallback_to_top(self):
        """Should fallback to zt when block too large."""
        block = Block(1, 30)  # 30 lines > 20 visible
        scroll_to, method, notes = _determine_scroll(block, 20)
        assert method == "zt"
        assert scroll_to == block.start


class TestNoScrollDirection:
    """Test _no_scroll_direction function."""

    def test_creates_no_scroll_direction(self):
        """Should create direction without scrolling."""
        block = Block(5, 10)
        visible = (1, 20)
        direction = _no_scroll_direction(block, visible)

        assert direction.needs_scroll is False
        assert direction.scroll_to is None
        assert direction.scroll_method is None
        assert direction.visible_range == visible


class TestScrollDirection:
    """Test _scroll_direction function."""

    def test_creates_scroll_direction(self):
        """Should create direction with scrolling."""
        block = Block(50, 55)
        direction, new_view = _scroll_direction(block, 20)

        assert direction.needs_scroll is True
        assert direction.scroll_to is not None
        assert direction.scroll_method is not None
        assert len(direction.commands) == 2


class TestDirectionForBlock:
    """Test _direction_for_block function."""

    def test_returns_no_scroll_when_visible(self):
        """Should not scroll when block is visible."""
        block = Block(5, 10)
        current_view = (1, 20)
        direction, new_view = _direction_for_block(block, current_view, 20)

        assert direction.needs_scroll is False
        assert new_view == current_view

    def test_returns_scroll_when_not_visible(self):
        """Should scroll when block is not visible."""
        block = Block(50, 55)
        current_view = (1, 20)
        direction, new_view = _direction_for_block(block, current_view, 20)

        assert direction.needs_scroll is True
        assert new_view != current_view


class TestCalculateStageDirections:
    """Test calculate_stage_directions function."""

    def test_single_block_in_view(self):
        """Should handle single block already in view."""
        blocks = [Block(5, 10)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)

        assert len(directions) == 1
        assert directions[0].needs_scroll is False

    def test_multiple_blocks(self):
        """Should calculate directions for multiple blocks."""
        blocks = [Block(5, 10), Block(50, 55), Block(100, 105)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)

        assert len(directions) == 3

    def test_overhead_subtracted(self):
        """Should subtract overhead from rows."""
        blocks = [Block(5, 10)]
        directions = calculate_stage_directions(rows=30, highlights=blocks, overhead=5)
        # visible_rows = 30 - 5 = 25
        assert len(directions) == 1

    def test_empty_blocks(self):
        """Should handle empty block list."""
        directions = calculate_stage_directions(rows=30, highlights=[])
        assert directions == []


class TestFormatDirectionsText:
    """Test format_directions_text function."""

    def test_format_basic_output(self):
        """Should format directions as text."""
        blocks = [Block(5, 10)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)
        result = format_directions_text(directions, 30)

        assert "Stage Directions for 30-row terminal" in result
        assert "Block 1" in result
        assert "lines 5-10" in result

    def test_format_with_scroll(self):
        """Should indicate scroll in output."""
        blocks = [Block(50, 55)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)
        result = format_directions_text(directions, 30)

        assert "Scroll:" in result or "Position:" in result

    def test_format_multiple_blocks(self):
        """Should format all blocks."""
        blocks = [Block(5, 10), Block(50, 55)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)
        result = format_directions_text(directions, 30)

        assert "Block 1" in result
        assert "Block 2" in result


class TestFormatDirectionText:
    """Test _format_direction_text function."""

    def test_format_scroll_direction(self):
        """Should format direction with scroll info."""
        block = Block(50, 55)
        direction = StageDirection(
            block=block,
            needs_scroll=True,
            scroll_to=52,
            scroll_method="zz",
            visible_range=(42, 62),
            commands=["52Gzz", "50GV55G"],
            notes=["Scroll to center block"],
        )
        lines = _format_direction_text(1, direction)

        assert any("Scroll:" in line for line in lines)
        assert any("52Gzz" in line for line in lines)

    def test_format_no_scroll_direction(self):
        """Should format direction without scroll."""
        block = Block(5, 10)
        direction = StageDirection(
            block=block,
            needs_scroll=False,
            scroll_to=None,
            scroll_method=None,
            visible_range=(1, 28),
            commands=["5GV10G"],
            notes=["Visible in current view"],
        )
        lines = _format_direction_text(1, direction)

        assert any("Position:" in line for line in lines)


class TestFormatDirectionsJson:
    """Test format_directions_json function."""

    def test_format_valid_json(self):
        """Should return valid JSON."""
        blocks = [Block(5, 10)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)
        result = format_directions_json(directions, 30)

        data = json.loads(result)
        assert "terminal_rows" in data
        assert "visible_rows" in data
        assert "blocks" in data

    def test_format_json_structure(self):
        """Should have correct JSON structure."""
        blocks = [Block(5, 10), Block(50, 55)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)
        result = format_directions_json(directions, 30)

        data = json.loads(result)
        assert data["terminal_rows"] == 30
        assert data["visible_rows"] == 28  # rows - 2 overhead
        assert len(data["blocks"]) == 2

    def test_format_json_block_fields(self):
        """Should include all block fields."""
        blocks = [Block(50, 55)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)
        result = format_directions_json(directions, 30)

        data = json.loads(result)
        block_data = data["blocks"][0]
        assert "lines" in block_data
        assert "size" in block_data
        assert "needs_scroll" in block_data
        assert "visible_range" in block_data
        assert "commands" in block_data


class TestFormatDirectionsDemorec:
    """Test format_directions_demorec function."""

    def test_format_demorec_output(self):
        """Should format as .demorec script."""
        blocks = [Block(5, 10)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)
        result = format_directions_demorec(directions)

        assert "# Generated stage directions" in result
        assert "# Block 1" in result
        assert 'Type "' in result
        assert "Sleep" in result

    def test_format_demorec_escape_between_blocks(self):
        """Should add Escape between blocks."""
        blocks = [Block(5, 10), Block(50, 55)]
        directions = calculate_stage_directions(rows=30, highlights=blocks)
        result = format_directions_demorec(directions)

        # Second block should have Escape before it
        lines = result.split("\n")
        block2_idx = next(i for i, l in enumerate(lines) if "Block 2" in l)
        # Check there's an Escape after Block 2 comment
        nearby_lines = lines[block2_idx : block2_idx + 3]
        assert any("Escape" in line for line in nearby_lines)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
