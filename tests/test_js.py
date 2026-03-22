"""Unit tests for JavaScript utilities."""

import pytest
from demorec.js import load_js, get_terminal_resize_js, TERMINAL_RESIZE_JS


class TestJsLoader:
    """Test JS file loading utilities."""
    
    def test_load_terminal_resize_js(self):
        """Should load terminal_resize.js content."""
        js = load_js("terminal_resize.js")
        assert len(js) > 0
        assert "initializeTerminal" in js
        assert "refineTerminalRows" in js
    
    def test_get_terminal_resize_js(self):
        """Should return terminal resize JS via helper function."""
        js = get_terminal_resize_js()
        assert "initializeTerminal" in js
        assert "refineTerminalRows" in js
    
    def test_preloaded_constant(self):
        """TERMINAL_RESIZE_JS should be preloaded."""
        assert TERMINAL_RESIZE_JS is not None
        assert len(TERMINAL_RESIZE_JS) > 100
        assert "initializeTerminal" in TERMINAL_RESIZE_JS
    
    def test_load_nonexistent_file_raises(self):
        """Should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            load_js("nonexistent.js")


class TestTerminalResizeJsContent:
    """Test the content of terminal_resize.js."""
    
    def test_contains_initialize_function(self):
        """Should contain initializeTerminal function."""
        assert "function initializeTerminal(config)" in TERMINAL_RESIZE_JS
    
    def test_contains_refine_function(self):
        """Should contain refineTerminalRows function."""
        assert "function refineTerminalRows(desiredRows)" in TERMINAL_RESIZE_JS
    
    def test_contains_container_styling(self):
        """Should contain viewport styling for container."""
        assert "100vw" in TERMINAL_RESIZE_JS
        assert "100vh" in TERMINAL_RESIZE_JS
    
    def test_contains_term_fit_call(self):
        """Should call term.fit() for resizing."""
        assert "term.fit()" in TERMINAL_RESIZE_JS
    
    def test_contains_font_size_calculation(self):
        """Should calculate font size for desired rows."""
        assert "baselineRows / config.desiredRows" in TERMINAL_RESIZE_JS
        assert "currentRows / desiredRows" in TERMINAL_RESIZE_JS
    
    def test_returns_rows_cols_fontSize(self):
        """Should return object with rows, cols, fontSize."""
        assert "rows:" in TERMINAL_RESIZE_JS
        assert "cols:" in TERMINAL_RESIZE_JS
        assert "fontSize:" in TERMINAL_RESIZE_JS
    
    def test_handles_missing_window_term(self):
        """Should handle case where window.term doesn't exist."""
        assert "if (!window.term) return null" in TERMINAL_RESIZE_JS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
