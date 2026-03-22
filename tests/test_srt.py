"""Unit tests for SRT subtitle generation."""

import pytest
import tempfile
from pathlib import Path

from demorec.runner import format_srt_time, split_caption, TimedNarration, Runner
from demorec.parser import Plan, Segment


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
        # Use exact decimal to avoid floating point issues
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


class TestTimedNarration:
    """Test TimedNarration dataclass."""
    
    def test_default_values(self):
        """Test default values for optional fields."""
        narration = TimedNarration(
            text="Hello world",
            mode="before",
            audio_path=Path("/tmp/test.mp3"),
            duration=2.5
        )
        
        assert narration.text == "Hello world"
        assert narration.mode == "before"
        assert narration.duration == 2.5
        assert narration.start_time == 0.0
        assert narration.cmd_index == 0
    
    def test_all_values(self):
        """Test with all fields specified."""
        narration = TimedNarration(
            text="Test narration",
            mode="after",
            audio_path=Path("/tmp/audio.mp3"),
            duration=3.0,
            start_time=10.5,
            cmd_index=5
        )
        
        assert narration.start_time == 10.5
        assert narration.cmd_index == 5


class TestRunnerSrtGeneration:
    """Test Runner._generate_srt method."""
    
    def test_generates_valid_srt_file(self):
        """Should generate valid SRT format."""
        # Create minimal plan
        plan = Plan(
            output=Path("/tmp/test.mp4"),
            width=1280,
            height=720,
            segments=[]
        )
        runner = Runner(plan)
        
        # Add test narrations
        runner.timed_narrations = [
            TimedNarration(
                text="First subtitle",
                mode="before",
                audio_path=Path("/tmp/1.mp3"),
                duration=2.0,
                start_time=0.0,
                cmd_index=0
            ),
            TimedNarration(
                text="Second subtitle",
                mode="after",
                audio_path=Path("/tmp/2.mp3"),
                duration=3.0,
                start_time=5.0,
                cmd_index=1
            ),
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)
        
        try:
            runner._generate_srt(srt_path)
            
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
        plan = Plan(
            output=Path("/tmp/test.mp4"),
            width=1280,
            height=720,
            segments=[]
        )
        runner = Runner(plan)
        
        runner.timed_narrations = [
            TimedNarration(
                text="Negative start",
                mode="before",
                audio_path=Path("/tmp/1.mp3"),
                duration=2.0,
                start_time=-1.0,  # Negative!
                cmd_index=0
            ),
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)
        
        try:
            runner._generate_srt(srt_path)
            
            content = srt_path.read_text()
            
            # Should start at 00:00:00, not negative
            assert "00:00:00,000 --> 00:00:02,000" in content
        finally:
            srt_path.unlink()
    
    def test_splits_long_captions(self):
        """Should split long caption text into multiple lines."""
        plan = Plan(
            output=Path("/tmp/test.mp4"),
            width=1280,
            height=720,
            segments=[]
        )
        runner = Runner(plan)
        
        long_text = "This is a very long caption that should be split into multiple lines for better readability"
        runner.timed_narrations = [
            TimedNarration(
                text=long_text,
                mode="before",
                audio_path=Path("/tmp/1.mp3"),
                duration=5.0,
                start_time=0.0,
                cmd_index=0
            ),
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            srt_path = Path(f.name)
        
        try:
            runner._generate_srt(srt_path)
            
            content = srt_path.read_text()
            
            # Should contain newlines within the caption block
            lines = content.split('\n')
            # Find caption lines (after timestamp)
            caption_lines = [l for l in lines if l and not l[0].isdigit() and '-->' not in l]
            
            # At least some should be split
            assert len(caption_lines) >= 2 or len(long_text) <= 42
        finally:
            srt_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
