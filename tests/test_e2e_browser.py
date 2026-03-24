"""End-to-end tests for browser mode recording and mode switching.

These tests spawn real subprocesses and have long timeouts.
Run with: pytest -m e2e
Skip with: pytest -m "not e2e"
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# Check if required dependencies are available
HAS_TTYD = shutil.which("ttyd") is not None
HAS_FFMPEG = shutil.which("ffmpeg") is not None

# Check if playwright chromium is installed
try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # Try to launch chromium to verify it's installed
        browser = p.chromium.launch()
        browser.close()
        HAS_PLAYWRIGHT = True
except Exception:
    HAS_PLAYWRIGHT = False

# Mark all tests in this module as e2e and slow, and skip if dependencies missing
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        not HAS_FFMPEG,
        reason="ffmpeg not installed - required for video encoding",
    ),
    pytest.mark.skipif(
        not HAS_PLAYWRIGHT,
        reason="playwright chromium not installed - run: playwright install chromium",
    ),
]


def run_demorec(script_content: str, output_name: str = "test_output.mp4"):
    """Helper to run demorec with a script."""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = Path(tmpdir) / "test.demorec"
        output_path = Path(tmpdir) / output_name
        
        # Update script to use temp output path
        script_content = script_content.replace(
            f"Output {output_name}", 
            f"Output {output_path}"
        )
        script_path.write_text(script_content)
        
        result = subprocess.run(
            ["demorec", "record", str(script_path)],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output_exists": output_path.exists(),
            "output_size": output_path.stat().st_size if output_path.exists() else 0
        }


class TestBrowserMode:
    """Test standalone browser mode recording."""
    
    def test_browser_navigate(self):
        """Test Navigate command."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode browser
Navigate "https://example.com"
Sleep 1s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed:\nstdout: {result['stdout']}\nstderr: {result['stderr']}"
        assert result["output_exists"], "Output video not created"
        assert result["output_size"] > 0, "Output video is empty"

    def test_browser_highlight_scroll(self):
        """Test Highlight, Unhighlight, and Scroll commands."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode browser
Navigate "https://example.com"
Sleep 1s
Highlight "h1"
Sleep 0.5s
Unhighlight "h1"
Scroll "down" 100
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed:\nstdout: {result['stdout']}\nstderr: {result['stderr']}"
        assert result["output_exists"], "Output video not created"

    def test_browser_wait(self):
        """Test Wait command."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode browser
Navigate "https://example.com"
Wait "h1"
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed:\nstdout: {result['stdout']}\nstderr: {result['stderr']}"
        assert result["output_exists"], "Output video not created"


@pytest.mark.skipif(
    not HAS_TTYD,
    reason="ttyd not installed - required for terminal recording in mode switching tests",
)
class TestModeSwitching:
    """Test mode switching between terminal and browser."""

    def test_terminal_to_browser(self):
        """Test switching from terminal to browser mode."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Type "echo hello"
Enter
Sleep 0.5s

@mode browser
Navigate "https://example.com"
Sleep 1s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed:\nstdout: {result['stdout']}\nstderr: {result['stderr']}"
        assert result["output_exists"], "Output video not created"
        # Check for segment concatenation message
        assert "Concatenating segments" in result["stdout"], "Missing concatenation step"

    def test_browser_to_terminal(self):
        """Test switching from browser to terminal mode."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode browser
Navigate "https://example.com"
Sleep 1s

@mode terminal
Type "echo 'back in terminal'"
Enter
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed:\nstdout: {result['stdout']}\nstderr: {result['stderr']}"
        assert result["output_exists"], "Output video not created"

    def test_roundtrip_terminal_browser_terminal(self):
        """Test full round-trip: terminal → browser → terminal."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Type "echo 'step 1'"
Enter
Sleep 0.5s

@mode browser
Navigate "https://example.com"
Sleep 1s

@mode terminal
Type "echo 'step 3'"
Enter
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed:\nstdout: {result['stdout']}\nstderr: {result['stderr']}"
        assert result["output_exists"], "Output video not created"
        # Should have 3 segments
        assert "3 commands)" in result["stdout"] or "segment" in result["stdout"].lower()


class TestAllBrowserCommands:
    """Test all browser commands work correctly."""
    
    def test_press_command(self):
        """Test Press command."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode browser
Navigate "https://example.com"
Sleep 1s
Press "Escape"
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed:\nstdout: {result['stdout']}\nstderr: {result['stderr']}"

    def test_screenshot_command(self):
        """Test Screenshot command."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode browser
Navigate "https://example.com"
Sleep 1s
Screenshot "test.png"
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed:\nstdout: {result['stdout']}\nstderr: {result['stderr']}"

    def test_hover_command(self):
        """Test Hover command."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode browser
Navigate "https://example.com"
Sleep 1s
Hover "a"
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed:\nstdout: {result['stdout']}\nstderr: {result['stderr']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
