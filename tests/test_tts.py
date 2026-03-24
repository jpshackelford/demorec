"""Unit tests for tts module.

Tests cover:
- EdgeTTS class
- ElevenLabsTTS class
- get_tts_engine factory
- estimate_duration
- get_audio_duration
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from demorec.tts import (
    EdgeTTS,
    ElevenLabsTTS,
    TTSEngine,
    estimate_duration,
    get_audio_duration,
    get_tts_engine,
)


class TestEdgeTTS:
    """Test EdgeTTS class."""

    def test_init_with_voice_name(self):
        """Should initialize with voice name lookup."""
        engine = EdgeTTS("jenny")
        assert engine.voice == "en-US-JennyNeural"

    def test_init_with_prefixed_voice(self):
        """Should handle edge: prefix."""
        engine = EdgeTTS("edge:jenny")
        assert engine.voice == "en-US-JennyNeural"

    def test_init_with_full_voice_name(self):
        """Should accept full voice name."""
        engine = EdgeTTS("en-US-JennyNeural")
        assert engine.voice == "en-US-JennyNeural"

    def test_init_with_unknown_voice_fallback(self):
        """Should fallback to Jenny for invalid voice."""
        engine = EdgeTTS("invalid")
        assert engine.voice == "en-US-JennyNeural"

    def test_available_voices(self):
        """Should have common voices available."""
        assert "jenny" in EdgeTTS.VOICES
        assert "guy" in EdgeTTS.VOICES
        assert "sonia" in EdgeTTS.VOICES  # UK
        assert "natasha" in EdgeTTS.VOICES  # AU

    def test_uk_voices(self):
        """Should have UK voices."""
        engine = EdgeTTS("sonia")
        assert "GB" in engine.voice

    def test_au_voices(self):
        """Should have AU voices."""
        engine = EdgeTTS("natasha")
        assert "AU" in engine.voice

    @pytest.mark.asyncio
    @patch("edge_tts.Communicate")
    async def test_synthesize_async(self, mock_communicate):
        """Should call edge_tts.Communicate correctly."""
        engine = EdgeTTS("jenny")
        mock_instance = MagicMock()
        mock_communicate.return_value = mock_instance

        async def mock_save(path):
            pass

        mock_instance.save = mock_save

        await engine._synthesize_async("Hello", Path("/tmp/test.mp3"))
        mock_communicate.assert_called_once_with("Hello", "en-US-JennyNeural")


class TestElevenLabsTTS:
    """Test ElevenLabsTTS class."""

    def test_init_without_api_key_raises(self):
        """Should raise if API key not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ELEVENLABS_API_KEY", None)
            with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
                ElevenLabsTTS()

    def test_init_with_api_key(self):
        """Should initialize with API key."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = ElevenLabsTTS()
            assert engine.api_key == "test_key"
            assert engine.voice_id == ElevenLabsTTS.VOICES["rachel"]

    def test_init_with_voice_name(self):
        """Should look up voice ID by name."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = ElevenLabsTTS("adam")
            assert engine.voice_id == ElevenLabsTTS.VOICES["adam"]

    def test_init_with_prefixed_voice(self):
        """Should handle eleven: prefix."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = ElevenLabsTTS("eleven:josh")
            assert engine.voice_id == ElevenLabsTTS.VOICES["josh"]

    def test_init_with_custom_voice_id(self):
        """Should accept custom voice ID."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = ElevenLabsTTS("CustomVoiceIdThatIsLong")
            assert engine.voice_id == "CustomVoiceIdThatIsLong"

    def test_init_with_short_unknown_voice_fallback(self):
        """Should fallback to rachel for short unknown voice."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = ElevenLabsTTS("xyz")  # Short, not in VOICES
            assert engine.voice_id == ElevenLabsTTS.VOICES["rachel"]

    def test_available_voices(self):
        """Should have common voices available."""
        assert "rachel" in ElevenLabsTTS.VOICES
        assert "adam" in ElevenLabsTTS.VOICES
        assert "bella" in ElevenLabsTTS.VOICES

    def test_build_payload(self):
        """Should build correct API payload."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = ElevenLabsTTS()
            payload = engine._build_payload("Hello world")
            import json

            data = json.loads(payload)
            assert data["text"] == "Hello world"
            assert data["model_id"] == "eleven_turbo_v2_5"
            assert "voice_settings" in data

    def test_build_headers(self):
        """Should build correct API headers."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = ElevenLabsTTS()
            headers = engine._build_headers()
            assert headers["Accept"] == "audio/mpeg"
            assert headers["Content-Type"] == "application/json"
            assert headers["xi-api-key"] == "test_key"


class TestGetTTSEngine:
    """Test get_tts_engine factory function."""

    def test_get_edge_engine(self):
        """Should return EdgeTTS for edge: prefix."""
        engine = get_tts_engine("edge:jenny")
        assert isinstance(engine, EdgeTTS)

    def test_get_eleven_engine_with_prefix(self):
        """Should return ElevenLabsTTS for eleven: prefix."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = get_tts_engine("eleven:rachel")
            assert isinstance(engine, ElevenLabsTTS)

    def test_get_eleven_engine_without_prefix(self):
        """Should default to ElevenLabs for unprefixed voice."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = get_tts_engine("rachel")
            assert isinstance(engine, ElevenLabsTTS)

    def test_get_default_engine(self):
        """Should default to ElevenLabs with rachel voice."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = get_tts_engine(None)
            assert isinstance(engine, ElevenLabsTTS)
            assert engine.voice_id == ElevenLabsTTS.VOICES["rachel"]

    def test_unknown_prefix_raises(self):
        """Should raise for unknown prefix."""
        with pytest.raises(ValueError, match="Unknown voice specifier"):
            get_tts_engine("unknown:voice")


class TestEstimateDuration:
    """Test estimate_duration function."""

    def test_estimate_single_word(self):
        """Should estimate duration for single word."""
        duration = estimate_duration("hello")
        assert duration > 0
        # 1 word at 150 wpm = 1/150 * 60 = 0.4 seconds
        assert abs(duration - 0.4) < 0.01

    def test_estimate_sentence(self):
        """Should estimate duration for sentence."""
        text = "This is a test sentence with seven words"
        duration = estimate_duration(text)
        word_count = len(text.split())
        # word_count words at 150 wpm = word_count/150 * 60 seconds
        expected = (word_count / 150) * 60
        assert abs(duration - expected) < 0.01

    def test_estimate_custom_wpm(self):
        """Should respect custom wpm."""
        duration = estimate_duration("hello", wpm=300)
        # 1 word at 300 wpm = 1/300 * 60 = 0.2 seconds
        assert abs(duration - 0.2) < 0.01

    def test_estimate_empty_text(self):
        """Should return 0 for empty text."""
        duration = estimate_duration("")
        assert duration == 0


class TestGetAudioDuration:
    """Test get_audio_duration function."""

    @patch("subprocess.run")
    def test_get_duration_success(self, mock_run):
        """Should return duration from ffprobe output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"format": {"duration": "5.123"}}',
        )

        duration = get_audio_duration(Path("/tmp/test.mp3"))
        assert duration == 5.123

    @patch("subprocess.run")
    def test_get_duration_failure(self, mock_run):
        """Should raise on ffprobe failure."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Error",
        )

        with pytest.raises(RuntimeError, match="ffprobe failed"):
            get_audio_duration(Path("/tmp/test.mp3"))


class TestTTSEngineProtocol:
    """Test TTSEngine protocol compliance."""

    def test_edge_tts_implements_protocol(self):
        """EdgeTTS should implement TTSEngine protocol."""
        engine = EdgeTTS()
        assert hasattr(engine, "synthesize")
        assert callable(engine.synthesize)

    def test_eleven_labs_implements_protocol(self):
        """ElevenLabsTTS should implement TTSEngine protocol."""
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            engine = ElevenLabsTTS()
            assert hasattr(engine, "synthesize")
            assert callable(engine.synthesize)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
