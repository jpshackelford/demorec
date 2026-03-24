"""End-to-end tests for terminal mode, especially rows/resize behavior.

These tests spawn real subprocesses and have long timeouts.
Run with: pytest -m e2e
Skip with: pytest -m "not e2e"
"""

import pytest
import subprocess
import tempfile
import re
from pathlib import Path

# Mark all tests in this module as e2e and slow
pytestmark = [pytest.mark.e2e, pytest.mark.slow]


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
            "output_size": output_path.stat().st_size if output_path.exists() else 0,
            "output_path": output_path
        }


class TestTerminalBasic:
    """Test basic terminal mode functionality."""
    
    def test_terminal_type_and_enter(self):
        """Test basic Type and Enter commands."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Type "echo hello world"
Enter
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"
        assert result["output_size"] > 0, "Output video is empty"

    def test_terminal_run_command(self):
        """Test Run command (type + enter combined)."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Run "ls -la"
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"

    def test_terminal_clear(self):
        """Test Clear command."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Type "echo test"
Enter
Sleep 0.3s
Clear
Sleep 0.3s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"


class TestTerminalRows:
    """Test @terminal:rows directive and resize behavior."""
    
    def test_terminal_rows_directive_accepted(self):
        """Test that @terminal:rows directive is accepted without error."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
@terminal:rows 30
Type "echo rows test"
Enter
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"

    def test_terminal_rows_small(self):
        """Test @terminal:rows with small row count (larger font)."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
@terminal:rows 20
Type "echo small rows = big font"
Enter
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"

    def test_terminal_rows_large(self):
        """Test @terminal:rows with large row count (smaller font)."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
@terminal:rows 40
Type "echo large rows = small font"
Enter
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"

    def test_terminal_rows_logs_actual_rows(self):
        """Verify that terminal logs actual row count achieved."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
@terminal:rows 30
Type "echo checking rows"
Enter
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        
        # Check stdout for row count info
        combined_output = result["stdout"] + result["stderr"]
        # Should log something about rows/terminal size
        assert "row" in combined_output.lower() or "terminal" in combined_output.lower(), \
            f"Expected row count logging, got: {combined_output[:500]}"


class TestTerminalVimPrimitives:
    """Test vim primitives in terminal mode."""
    
    def test_vim_open_close(self):
        """Test Open and Close vim primitives."""
        # First create a test file
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Run "echo 'test content' > /tmp/test_vim.py"
Open "/tmp/test_vim.py"
Sleep 1s
Close
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"

    def test_vim_highlight(self):
        """Test Highlight vim primitive."""
        # Create a multi-line test file first
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Run "printf 'line1\\nline2\\nline3\\nline4\\nline5\\n' > /tmp/test_hl.py"
Open "/tmp/test_hl.py"
Sleep 0.5s
Highlight "2-4"
Sleep 1s
Close
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"

    def test_vim_goto(self):
        """Test Goto vim primitive."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Run "seq 1 50 > /tmp/test_goto.txt"
Open "/tmp/test_goto.txt"
Sleep 0.5s
Goto 25
Sleep 1s
Close
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"


class TestTerminalWithNarration:
    """Test terminal with narration timing."""
    
    def test_terminal_before_narration(self):
        """Test narration with 'before' timing."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Type "echo hello" -> "Typing hello" @before
Enter
Sleep 0.5s
'''
        result = run_demorec(script)
        # May fail if TTS not configured, but should parse correctly
        # Just check it doesn't crash on parsing
        assert "syntax error" not in result["stderr"].lower(), \
            f"Syntax error: {result['stderr']}"

    def test_terminal_after_narration(self):
        """Test narration with 'after' timing."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Run "ls" -> "Listing files" @after
Sleep 0.5s
'''
        result = run_demorec(script)
        assert "syntax error" not in result["stderr"].lower(), \
            f"Syntax error: {result['stderr']}"


class TestTerminalEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_terminal_segment(self):
        """Test terminal segment with no commands (just mode switch)."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Sleep 1s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"

    def test_special_characters_in_type(self):
        """Test typing special characters."""
        script = '''Output test_output.mp4
Set Width 1280
Set Height 720

@mode terminal
Type "echo $HOME"
Enter
Sleep 0.5s
Type "echo 'single quotes'"
Enter
Sleep 0.5s
'''
        result = run_demorec(script)
        assert result["returncode"] == 0, f"Failed: {result['stderr']}"
        assert result["output_exists"], "Output video not created"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
