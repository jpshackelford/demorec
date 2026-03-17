"""Text-to-speech synthesis for narration."""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Protocol


class TTSEngine(Protocol):
    """Protocol for TTS engines."""
    
    def synthesize(self, text: str, output_path: Path) -> None:
        """Synthesize speech from text and save to output_path (MP3)."""
        ...


class EdgeTTS:
    """Microsoft Edge TTS - high quality, free."""
    
    # Popular voices
    VOICES = {
        # English US
        "jenny": "en-US-JennyNeural",
        "guy": "en-US-GuyNeural",
        "aria": "en-US-AriaNeural",
        "davis": "en-US-DavisNeural",
        "amber": "en-US-AmberNeural",
        "ana": "en-US-AnaNeural",
        "andrew": "en-US-AndrewNeural",
        "emma": "en-US-EmmaNeural",
        "brian": "en-US-BrianNeural",
        "christopher": "en-US-ChristopherNeural",
        # English UK
        "sonia": "en-GB-SoniaNeural",
        "ryan": "en-GB-RyanNeural",
        "libby": "en-GB-LibbyNeural",
        # English AU
        "natasha": "en-AU-NatashaNeural",
        "william": "en-AU-WilliamNeural",
    }
    
    def __init__(self, voice: str = "jenny"):
        # Parse voice name (e.g., "edge:jenny" -> "jenny")
        if ":" in voice:
            voice = voice.split(":", 1)[1]
        
        # Look up voice or use as-is if it's a full voice name
        self.voice = self.VOICES.get(voice.lower(), voice)
        if not self.voice.endswith("Neural"):
            # Fallback to Jenny if invalid
            self.voice = self.VOICES["jenny"]
    
    def synthesize(self, text: str, output_path: Path) -> None:
        """Synthesize speech using edge-tts."""
        # edge-tts is async, so we need to run it
        asyncio.run(self._synthesize_async(text, output_path))
    
    async def _synthesize_async(self, text: str, output_path: Path) -> None:
        import edge_tts
        
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(str(output_path))


class ElevenLabsTTS:
    """ElevenLabs TTS engine (requires paid subscription for API voices)."""
    
    VOICES = {
        "rachel": "21m00Tcm4TlvDq8ikWAM",
        "adam": "pNInz6obpgDQGcFmaJgB", 
        "josh": "TxGEqnHWrfWFTfGW9XjX",
        "bella": "EXAVITQu4vr4xnSDxMaL",
        "sam": "yoZ06aMxZJJ28mfd3POQ",
    }
    
    def __init__(self, voice: str = "rachel"):
        self.api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY environment variable not set")
        
        if ":" in voice:
            voice = voice.split(":", 1)[1]
        
        self.voice_id = self.VOICES.get(voice.lower(), self.VOICES["rachel"])
    
    def synthesize(self, text: str, output_path: Path) -> None:
        """Synthesize speech using ElevenLabs API."""
        import urllib.request
        import json
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        
        payload = json.dumps({
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }).encode("utf-8")
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        
        with urllib.request.urlopen(req) as response:
            with open(output_path, "wb") as f:
                f.write(response.read())


def get_tts_engine(voice: str | None) -> TTSEngine:
    """Get the appropriate TTS engine for the given voice specifier.
    
    Supported formats:
        edge:jenny    - Microsoft Edge TTS (default, free, high quality)
        edge:guy      - Male voice
        eleven:rachel - ElevenLabs (requires paid API)
    """
    if voice is None:
        voice = "edge:jenny"  # Default to Edge TTS
    
    if voice.startswith("eleven:"):
        return ElevenLabsTTS(voice)
    elif voice.startswith("edge:") or ":" not in voice:
        return EdgeTTS(voice)
    else:
        raise ValueError(f"Unknown voice specifier: {voice}")


def estimate_duration(text: str, wpm: int = 150) -> float:
    """Estimate speech duration in seconds based on word count."""
    words = len(text.split())
    return (words / wpm) * 60


def get_audio_duration(audio_path: Path) -> float:
    """Get the duration of an audio file in seconds using ffprobe."""
    import subprocess
    import json
    
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(audio_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
