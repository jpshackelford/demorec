"""Unit tests for audio/SRT utilities in audio.py.

Tests cover:
- format_srt_time: SRT timestamp formatting
- split_caption: Text line wrapping
- _word_wrap: Word wrapping helper
- generate_srt: Full SRT file generation
- Other audio utility functions
"""

import pytest
import tempfile
from pathlib import Path
from dataclasses import dataclass

from demorec.audio import (
    format_srt_time,
    split_caption,
    generate_srt,
    _word_wrap,
    get_duration,
    write_concat_file,
    _build_audio_filter,
)


class TestFormatSrtTime:
    """Test format_srt_time function."""

    def test_zero_seconds(self):
        """Test formatting 0 seconds."""
        assert format_srt_time(0) == "00:00:00,000"

    def test_sub_second(self):
        """Test formatting sub-second times."""
        assert format_srt_time(0.5) == "00:00:00,500"
        assert format_srt_time(0.123) == "00:00:00,123"
        assert format_srt_time(0.999) == "00:00:00,999"

    def test_seconds_only(self):
        """Test formatting seconds without minutes."""
        assert format_srt_time(5.0) == "00:00:05,000"
        assert format_srt_time(45.5) == "00:00:45,500"
        assert format_srt_time(59.999) == "00:00:59,999"

    def test_minutes_and_seconds(self):
        """Test formatting with minutes."""
        assert format_srt_time(60.0) == "00:01:00,000"
        assert format_srt_time(90.5) == "00:01:30,500"
        assert format_srt_time(125.25) == "00:02:05,250"

    def test_hours(self):
        """Test formatting with hours."""
        assert format_srt_time(3600.0) == "01:00:00,000"
        assert format_srt_time(3661.5) == "01:01:01,500"
        assert format_srt_time(7325.125) == "02:02:05,125"

    def test_large_values(self):
        """Test formatting large time values."""
        # 10 hours, 30 minutes, 45 seconds, 500ms
        assert format_srt_time(37845.5) == "10:30:45,500"


class TestSplitCaption:
    """Test split_caption function."""

    def test_short_caption_unchanged(self):
        """Short captions should remain as single line."""
        text = "This is a short caption."
        result = split_caption(text)
        assert result == ["This is a short caption."]

    def test_exactly_max_length(self):
        """Caption at exactly max length should be single line."""
        text = "a" * 42
        result = split_caption(text, max_len=42)
        assert result == [text]

    def test_splits_at_word_boundary(self):
        """Long captions should split at word boundaries."""
        text = "This is a much longer caption that needs to be split into multiple lines for readability"
        result = split_caption(text, max_len=42)

        assert len(result) > 1
        # Each line should be <= max_len
        for line in result:
            assert len(line) <= 42
        # All words should be preserved
        assert " ".join(result) == text

    def test_custom_max_length(self):
        """Should respect custom max_len parameter."""
        text = "This is a test sentence for splitting."
        result = split_caption(text, max_len=20)
        for line in result:
            assert len(line) <= 20

    def test_single_long_word(self):
        """Single word longer than max should be on its own line."""
        text = "Short superlongwordthatexceedslimit end"
        result = split_caption(text, max_len=20)
        # The long word should be on its own line
        assert any("superlongwordthatexceedslimit" in line for line in result)

    def test_empty_string(self):
        """Empty string should return list with empty string."""
        result = split_caption("")
        assert result == [""]

    def test_preserves_all_words(self):
        """All words should be preserved after splitting."""
        text = "The quick brown fox jumps over the lazy dog multiple times to make this sentence longer"
        result = split_caption(text, max_len=30)
        # Rejoin and compare
        rejoined = " ".join(result)
        assert rejoined == text


class TestWordWrap:
    """Test _word_wrap helper function."""

    def test_empty_list(self):
        """Empty word list should return empty list."""
        result = _word_wrap([], 42)
        assert result == []

    def test_single_word(self):
        """Single word should return single line."""
        result = _word_wrap(["hello"], 42)
        assert result == ["hello"]

    def test_multiple_words_fit(self):
        """Words that fit in one line should stay together."""
        result = _word_wrap(["hello", "world"], 20)
        assert result == ["hello world"]

    def test_multiple_lines(self):
        """Words that don't fit should be split into multiple lines."""
        result = _word_wrap(["hello", "world", "this", "is", "test"], 12)
        assert len(result) > 1


@dataclass
class MockNarration:
    """Mock narration object for testing SRT generation."""
    text: str
    start_time: float
    duration: float


class TestGenerateSrt:
    """Test generate_srt function."""

    def test_generates_valid_srt_file(self):
        """Should generate valid SRT format."""
        narrations = [
            MockNarration(text="First subtitle", start_time=0.0, duration=2.0),
            MockNarration(text="Second subtitle", start_time=5.0, duration=3.0),
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)

        try:
            generate_srt(narrations, srt_path)
            content = srt_path.read_text()

            # Check structure
            assert "1\n" in content
            assert "2\n" in content
            assert "00:00:00,000 --> 00:00:02,000" in content
            assert "00:00:05,000 --> 00:00:08,000" in content
            assert "First subtitle" in content
            assert "Second subtitle" in content
        finally:
            srt_path.unlink()

    def test_handles_negative_start_time(self):
        """Should clamp negative start times to 0."""
        narrations = [
            MockNarration(text="Negative start", start_time=-1.0, duration=2.0),
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)

        try:
            generate_srt(narrations, srt_path)
            content = srt_path.read_text()
            # Should start at 00:00:00, not negative
            assert "00:00:00,000 --> 00:00:02,000" in content
        finally:
            srt_path.unlink()

    def test_splits_long_captions(self):
        """Should split long caption text into multiple lines."""
        long_text = "This is a very long caption that should be split into multiple lines for better readability"
        narrations = [
            MockNarration(text=long_text, start_time=0.0, duration=5.0),
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)

        try:
            generate_srt(narrations, srt_path)
            content = srt_path.read_text()
            # Should contain all the text (possibly split)
            assert "caption" in content
        finally:
            srt_path.unlink()

    def test_empty_narrations(self):
        """Should handle empty narration list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)

        try:
            generate_srt([], srt_path)
            content = srt_path.read_text()
            assert content == ""
        finally:
            srt_path.unlink()


class TestWriteConcatFile:
    """Test write_concat_file function."""

    def test_writes_file_list(self):
        """Should write FFmpeg concat file format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "concat.txt"
            files = [Path("/path/to/file1.mp3"), Path("/path/to/file2.mp3")]
            write_concat_file(output, files)
            
            content = output.read_text()
            assert "file '/path/to/file1.mp3'" in content
            assert "file '/path/to/file2.mp3'" in content

    def test_empty_file_list(self):
        """Should handle empty file list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "concat.txt"
            write_concat_file(output, [])
            content = output.read_text()
            assert content == ""


class TestBuildAudioFilter:
    """Test _build_audio_filter function."""

    def test_single_narration(self):
        """Should build filter for single narration."""
        narrations = [MockNarration(text="Test", start_time=1.0, duration=2.0)]
        filter_str = _build_audio_filter(narrations)
        assert "adelay=1000|1000" in filter_str
        assert "[a0]" in filter_str
        assert "apad" in filter_str

    def test_multiple_narrations(self):
        """Should build amix filter for multiple narrations."""
        narrations = [
            MockNarration(text="First", start_time=0.0, duration=2.0),
            MockNarration(text="Second", start_time=5.0, duration=3.0),
        ]
        filter_str = _build_audio_filter(narrations)
        assert "amix=inputs=2" in filter_str
        assert "[a0]" in filter_str
        assert "[a1]" in filter_str

    def test_negative_start_time_clamped(self):
        """Should clamp negative start times to 0."""
        narrations = [MockNarration(text="Test", start_time=-1.0, duration=2.0)]
        filter_str = _build_audio_filter(narrations)
        assert "adelay=0|0" in filter_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
