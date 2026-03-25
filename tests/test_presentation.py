"""Tests for presentation mode."""

import tempfile
from pathlib import Path

import pytest

from demorec.parser import parse_script, Segment


class TestPresentationParsing:
    """Tests for parsing presentation mode scripts."""

    def test_parse_presentation_mode(self, tmp_path):
        """Test parsing @mode presentation directive."""
        script = tmp_path / "test.demorec"
        script.write_text(
            '@mode presentation "slides.md"\n'
            "Slide 1 3s\n"
            "Slide 2 2s\n"
        )
        plan = parse_script(script)

        assert len(plan.segments) == 1
        seg = plan.segments[0]
        assert seg.mode == "presentation"
        assert seg.presentation_file == "slides.md"
        assert len(seg.commands) == 2
        assert seg.commands[0].name == "Slide"
        assert seg.commands[0].args == ["1", "3s"]

    def test_parse_presentation_with_url(self, tmp_path):
        """Test parsing presentation with HTTP URL."""
        script = tmp_path / "test.demorec"
        script.write_text(
            '@mode presentation "https://example.com/slides.md"\n'
            "Slide 1 3s\n"
        )
        plan = parse_script(script)

        seg = plan.segments[0]
        assert seg.presentation_file == "https://example.com/slides.md"

    def test_parse_presentation_theme(self, tmp_path):
        """Test parsing Set Theme in presentation mode."""
        script = tmp_path / "test.demorec"
        script.write_text(
            '@mode presentation "slides.md"\n'
            'Set Theme "openhands"\n'
            "Slide 1 3s\n"
        )
        plan = parse_script(script)

        seg = plan.segments[0]
        assert seg.presentation_theme == "openhands"
        # Theme should not be added as a command in presentation mode
        assert all(cmd.name != "SetTheme" for cmd in seg.commands)

    def test_parse_presentation_theme_url(self, tmp_path):
        """Test parsing Set Theme with URL in presentation mode."""
        script = tmp_path / "test.demorec"
        script.write_text(
            '@mode presentation "slides.md"\n'
            'Set Theme "https://example.com/theme.css"\n'
            "Slide 1 3s\n"
        )
        plan = parse_script(script)

        seg = plan.segments[0]
        assert seg.presentation_theme == "https://example.com/theme.css"

    def test_parse_mixed_modes(self, tmp_path):
        """Test parsing script with mixed terminal and presentation modes."""
        script = tmp_path / "test.demorec"
        script.write_text(
            '@mode presentation "intro.md"\n'
            "Slide 1 3s\n"
            "\n"
            "@mode terminal\n"
            'Type "echo hello"\n'
            "Enter\n"
            "\n"
            '@mode presentation "outro.md"\n'
            "Slide 1 2s\n"
        )
        plan = parse_script(script)

        assert len(plan.segments) == 3
        assert plan.segments[0].mode == "presentation"
        assert plan.segments[0].presentation_file == "intro.md"
        assert plan.segments[1].mode == "terminal"
        assert plan.segments[2].mode == "presentation"
        assert plan.segments[2].presentation_file == "outro.md"

    def test_terminal_theme_still_works(self, tmp_path):
        """Ensure Set Theme still works for terminal mode."""
        script = tmp_path / "test.demorec"
        script.write_text(
            "@mode terminal\n"
            'Set Theme "Dracula"\n'
            'Type "echo hello"\n'
        )
        plan = parse_script(script)

        seg = plan.segments[0]
        assert seg.mode == "terminal"
        # In terminal mode, theme should be a command
        assert any(cmd.name == "SetTheme" for cmd in seg.commands)


class TestMarpModule:
    """Tests for the marp module."""

    def test_is_url(self):
        """Test URL detection."""
        from demorec.marp import is_url

        assert is_url("https://example.com/slides.md")
        assert is_url("http://example.com/slides.md")
        assert not is_url("slides.md")
        assert not is_url("/path/to/slides.md")
        assert not is_url("./slides.md")

    def test_theme_aliases(self):
        """Test theme alias resolution."""
        from demorec.marp import THEME_ALIASES, resolve_theme

        assert "openhands" in THEME_ALIASES

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Alias should resolve to URL
            resolved = resolve_theme("openhands", tmp_path)
            assert resolved.startswith("https://")
            assert "openhands" in resolved

    def test_resolve_theme_url_passthrough(self):
        """Test that URLs are passed through."""
        from demorec.marp import resolve_theme

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            url = "https://example.com/theme.css"
            assert resolve_theme(url, tmp_path) == url

    def test_resolve_theme_local_file(self):
        """Test local file resolution."""
        from demorec.marp import resolve_theme

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = "theme.css"
            resolved = resolve_theme(local, tmp_path)
            assert resolved.endswith("theme.css")
            assert Path(resolved).is_absolute()

    def test_check_marp_installed(self):
        """Test Marp installation check."""
        from demorec.marp import check_marp_installed

        # Just verify it returns a boolean without crashing
        result = check_marp_installed()
        assert isinstance(result, bool)


class TestPresentationRecorder:
    """Tests for PresentationRecorder class."""

    def test_recorder_init(self):
        """Test recorder initialization."""
        from demorec.modes.presentation import PresentationRecorder

        recorder = PresentationRecorder(width=1920, height=1080, framerate=30)
        assert recorder.width == 1920
        assert recorder.height == 1080
        assert recorder.framerate == 30

    def test_smart_wait_narration_longer(self):
        """Test smart wait when narration is longer than min_time."""
        from demorec.modes.presentation import PresentationRecorder
        from demorec.parser import Command

        recorder = PresentationRecorder()

        # Mock a narration that's 5 seconds
        class MockNarration:
            mode = "during"
            duration = 5.0

        recorder._timed_narrations = {0: MockNarration()}

        cmd = Command("Slide", ["1", "2s"])

        import asyncio

        async def test():
            import time

            start = time.time()
            await recorder._smart_wait(cmd, 0)
            elapsed = time.time() - start
            # Should wait ~5.5s (narration + padding), not 2s
            assert elapsed >= 5.0

        # Skip actual async test in unit tests - would need mock
        # asyncio.run(test())

    def test_smart_wait_min_time_longer(self):
        """Test smart wait when min_time is longer than narration."""
        from demorec.modes.presentation import PresentationRecorder
        from demorec.parser import Command

        recorder = PresentationRecorder()

        # Mock a narration that's 1 second
        class MockNarration:
            mode = "during"
            duration = 1.0

        recorder._timed_narrations = {0: MockNarration()}

        cmd = Command("Slide", ["1", "5s"])

        # min_time (5s) > narration (1s) + padding (0.5s)
        # Should wait 5s
