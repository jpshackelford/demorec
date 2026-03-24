"""Unit tests for cli module.

Tests cover:
- Voice configuration data
- _print_plan_summary
- _parse_and_configure
- _parse_blocks
- _output_directions
- _get_screenshot_mode
- _get_terminal_segment
- CLI command structure
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from demorec.cli import (
    EDGE_VOICES,
    ELEVEN_VOICES,
    _get_screenshot_mode,
    _get_terminal_segment,
    _output_directions,
    _parse_and_configure,
    _parse_blocks,
    _print_plan_summary,
    main,
)
from demorec.parser import Plan, Segment


class TestVoiceConfiguration:
    """Test voice configuration data."""

    def test_edge_voices_dict(self):
        """Should have edge voices as dict."""
        assert isinstance(EDGE_VOICES, dict)
        assert "jenny" in EDGE_VOICES
        assert "guy" in EDGE_VOICES

    def test_edge_voices_descriptions(self):
        """Should have descriptions for edge voices."""
        assert EDGE_VOICES["jenny"] == "Female, US"
        assert EDGE_VOICES["sonia"] == "Female, UK"
        assert EDGE_VOICES["natasha"] == "Female, AU"

    def test_eleven_voices_list(self):
        """Should have eleven voices as list."""
        assert isinstance(ELEVEN_VOICES, list)
        assert "rachel" in ELEVEN_VOICES
        assert "adam" in ELEVEN_VOICES


class TestPrintPlanSummary:
    """Test _print_plan_summary function."""

    def test_prints_plan_info(self):
        """Should print plan output and segments."""
        plan = Plan(
            output=Path("test.mp4"),
            segments=[
                Segment(mode="terminal", commands=[MagicMock()] * 3),
                Segment(mode="browser", commands=[MagicMock()] * 2),
            ],
        )
        with patch("demorec.cli.console") as mock_console:
            _print_plan_summary(plan)
            assert mock_console.print.call_count >= 3  # output, segments count, + each segment


class TestParseAndConfigure:
    """Test _parse_and_configure function."""

    def test_parse_basic_script(self):
        """Should parse script and return plan."""
        script = """
Output test.mp4
@mode terminal
Type "hello"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = _parse_and_configure(path, None, None)
            assert plan.output == Path("test.mp4")
        finally:
            path.unlink()

    def test_parse_with_output_override(self):
        """Should override output from script."""
        script = """
Output original.mp4
@mode terminal
Type "hello"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = _parse_and_configure(path, Path("override.mp4"), None)
            assert plan.output == Path("override.mp4")
        finally:
            path.unlink()

    def test_parse_with_voice_override(self):
        """Should override voice from script."""
        script = """
@mode terminal
Type "hello"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = _parse_and_configure(path, None, "edge:jenny")
            assert plan.voice == "edge:jenny"
        finally:
            path.unlink()


class TestParseBlocks:
    """Test _parse_blocks function."""

    def test_parse_valid_highlights(self):
        """Should parse valid highlight string."""
        blocks = _parse_blocks("6-7,11-16,26-34")
        assert len(blocks) == 3
        assert blocks[0].start == 6
        assert blocks[0].end == 7

    def test_parse_single_line(self):
        """Should parse single line highlight."""
        blocks = _parse_blocks("15")
        assert len(blocks) == 1
        assert blocks[0].start == 15
        assert blocks[0].end == 15


class TestOutputDirections:
    """Test _output_directions function."""

    def test_output_text_format(self, capsys):
        """Should output text format."""
        from demorec.stage import Block, calculate_stage_directions

        blocks = [Block(5, 10)]
        directions = calculate_stage_directions(30, blocks)
        _output_directions(directions, 30, "text")
        captured = capsys.readouterr()
        assert "Stage Directions" in captured.out

    def test_output_json_format(self, capsys):
        """Should output JSON format."""
        from demorec.stage import Block, calculate_stage_directions
        import json

        blocks = [Block(5, 10)]
        directions = calculate_stage_directions(30, blocks)
        _output_directions(directions, 30, "json")
        captured = capsys.readouterr()
        # Should be valid JSON
        data = json.loads(captured.out)
        assert "terminal_rows" in data

    def test_output_demorec_format(self, capsys):
        """Should output .demorec format."""
        from demorec.stage import Block, calculate_stage_directions

        blocks = [Block(5, 10)]
        directions = calculate_stage_directions(30, blocks)
        _output_directions(directions, 30, "demorec")
        captured = capsys.readouterr()
        assert "# Generated stage directions" in captured.out


class TestGetScreenshotMode:
    """Test _get_screenshot_mode function."""

    def test_screenshots_true(self):
        """Should return 'always' when True."""
        assert _get_screenshot_mode(True) == "always"

    def test_screenshots_false(self):
        """Should return 'never' when False."""
        assert _get_screenshot_mode(False) == "never"

    def test_screenshots_none(self):
        """Should return 'on_error' when None."""
        assert _get_screenshot_mode(None) == "on_error"


class TestGetTerminalSegment:
    """Test _get_terminal_segment function."""

    def test_returns_terminal_segment(self):
        """Should return first terminal segment with commands."""
        from demorec.parser import Command

        script = """
@mode terminal
Type "hello"
Enter
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            segment = _get_terminal_segment(path)
            assert segment.mode == "terminal"
            assert len(segment.commands) > 0
        finally:
            path.unlink()

    def test_raises_for_no_terminal_segment(self):
        """Should raise SystemExit if no terminal segment."""
        script = """
@mode browser
Navigate "https://example.com"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            with pytest.raises(SystemExit):
                _get_terminal_segment(path)
        finally:
            path.unlink()


class TestCLIMain:
    """Test CLI main command group."""

    def test_main_group_exists(self):
        """Should have main command group."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "demorec" in result.output.lower() or "demo" in result.output.lower()

    def test_version_option(self):
        """Should show version."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "demorec" in result.output.lower()


class TestCLIRecord:
    """Test CLI record command."""

    def test_record_help(self):
        """Should show record help."""
        runner = CliRunner()
        result = runner.invoke(main, ["record", "--help"])
        assert result.exit_code == 0
        assert "script" in result.output.lower()

    def test_record_dry_run(self):
        """Should support dry-run option."""
        script = """
Output test.mp4
@mode terminal
Type "hello"
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.demorec", "w") as f:
                f.write(script)
            result = runner.invoke(main, ["record", "test.demorec", "--dry-run"])
            assert result.exit_code == 0
            assert "Dry run" in result.output


class TestCLIValidate:
    """Test CLI validate command."""

    def test_validate_valid_script(self):
        """Should validate valid script."""
        script = """
Output test.mp4
@mode terminal
Type "hello"
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.demorec", "w") as f:
                f.write(script)
            result = runner.invoke(main, ["validate", "test.demorec"])
            assert result.exit_code == 0
            assert "Valid" in result.output


class TestCLIVoices:
    """Test CLI voices command."""

    def test_voices_lists_edge(self):
        """Should list edge voices."""
        runner = CliRunner()
        result = runner.invoke(main, ["voices"])
        assert result.exit_code == 0
        assert "edge" in result.output.lower()
        assert "jenny" in result.output.lower()

    def test_voices_lists_eleven(self):
        """Should list eleven labs voices."""
        runner = CliRunner()
        result = runner.invoke(main, ["voices"])
        assert result.exit_code == 0
        assert "eleven" in result.output.lower()


class TestCLIStage:
    """Test CLI stage command."""

    def test_stage_with_rows_and_highlights(self):
        """Should calculate stage directions."""
        runner = CliRunner()
        result = runner.invoke(main, ["stage", "--rows", "30", "--highlights", "6-10"])
        assert result.exit_code == 0
        assert "Stage Directions" in result.output or "Block" in result.output

    def test_stage_json_format(self):
        """Should output JSON format."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["stage", "--rows", "30", "--highlights", "6-10", "--format", "json"]
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "terminal_rows" in data

    def test_stage_demorec_format(self):
        """Should output .demorec format."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["stage", "--rows", "30", "--highlights", "6-10", "--format", "demorec"]
        )
        assert result.exit_code == 0
        assert "# Generated" in result.output


class TestCLICheckpoints:
    """Test CLI checkpoints command."""

    def test_checkpoints_from_script(self):
        """Should detect checkpoints from script."""
        script = """
@mode terminal
Type "vim file.py"
Enter
Type "10G"
Type "V"
Type "20G"
Escape
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.demorec", "w") as f:
                f.write(script)
            result = runner.invoke(main, ["checkpoints", "test.demorec"])
            assert result.exit_code == 0

    def test_checkpoints_json_format(self):
        """Should output checkpoints as JSON."""
        script = """
@mode terminal
Type "hello"
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("test.demorec", "w") as f:
                f.write(script)
            result = runner.invoke(main, ["checkpoints", "test.demorec", "--format", "json"])
            assert result.exit_code == 0
            import json

            # Find the JSON block in output - it starts with { and ends with }
            lines = result.output.strip().split("\n")
            # Find the start of JSON output
            json_start = None
            for i, line in enumerate(lines):
                if line.strip().startswith("{"):
                    json_start = i
                    break
            
            if json_start is not None:
                json_text = "\n".join(lines[json_start:])
                data = json.loads(json_text)
                assert "checkpoint_count" in data


class TestCLIInstall:
    """Test CLI install command."""

    def test_install_help(self):
        """Should show install help."""
        runner = CliRunner()
        result = runner.invoke(main, ["install", "--help"])
        assert result.exit_code == 0
        assert "playwright" in result.output.lower() or "browser" in result.output.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
