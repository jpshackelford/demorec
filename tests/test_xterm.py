"""Unit tests for xterm.js terminal configuration utilities.

Tests cover:
- JS file loading (_load_js function)
- JS template constants
- TerminalConfig dataclass
- TerminalSize dataclass
- Helper functions
"""

import pytest
from demorec.xterm import (
    _load_js,
    SETUP_TERMINAL_JS,
    FIT_TO_ROWS_JS,
    GET_BUFFER_STATE_JS,
    SETUP_CONTAINER_JS,
    TerminalConfig,
    TerminalSize,
    _config_to_dict,
    _parse_terminal_result,
)


class TestLoadJs:
    """Test JS file loading utility."""

    def test_load_setup_terminal_js(self):
        """Should load setup_terminal.js content."""
        js = _load_js("setup_terminal.js")
        assert len(js) > 0
        assert isinstance(js, str)

    def test_load_fit_to_rows_js(self):
        """Should load fit_to_rows.js content."""
        js = _load_js("fit_to_rows.js")
        assert len(js) > 0

    def test_load_get_buffer_state_js(self):
        """Should load get_buffer_state.js content."""
        js = _load_js("get_buffer_state.js")
        assert len(js) > 0

    def test_load_setup_container_js(self):
        """Should load setup_container.js content."""
        js = _load_js("setup_container.js")
        assert len(js) > 0

    def test_load_nonexistent_file_raises(self):
        """Should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            _load_js("nonexistent.js")


class TestJsConstants:
    """Test preloaded JS constants."""

    def test_setup_terminal_js_loaded(self):
        """SETUP_TERMINAL_JS should be preloaded."""
        assert SETUP_TERMINAL_JS is not None
        assert len(SETUP_TERMINAL_JS) > 100

    def test_fit_to_rows_js_loaded(self):
        """FIT_TO_ROWS_JS should be preloaded."""
        assert FIT_TO_ROWS_JS is not None
        assert len(FIT_TO_ROWS_JS) > 50

    def test_get_buffer_state_js_loaded(self):
        """GET_BUFFER_STATE_JS should be preloaded."""
        assert GET_BUFFER_STATE_JS is not None
        assert len(GET_BUFFER_STATE_JS) > 50

    def test_setup_container_js_loaded(self):
        """SETUP_CONTAINER_JS should be preloaded."""
        assert SETUP_CONTAINER_JS is not None
        assert len(SETUP_CONTAINER_JS) > 50


class TestSetupTerminalJsContent:
    """Test the content of setup_terminal.js."""

    def test_contains_term_reference(self):
        """Should reference window.term."""
        assert "term" in SETUP_TERMINAL_JS.lower()

    def test_contains_font_sizing(self):
        """Should handle font sizing."""
        assert "font" in SETUP_TERMINAL_JS.lower()


class TestFitToRowsJsContent:
    """Test the content of fit_to_rows.js."""

    def test_contains_rows_reference(self):
        """Should reference rows for resizing."""
        assert "rows" in FIT_TO_ROWS_JS.lower()


class TestTerminalConfig:
    """Test TerminalConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TerminalConfig()
        assert config.font_size == 14
        assert config.font_family is not None
        assert config.line_height == 1.0
        assert config.theme is None
        assert config.desired_rows is None

    def test_custom_values(self):
        """Test custom configuration values."""
        config = TerminalConfig(
            font_size=16,
            font_family="Courier",
            line_height=1.2,
            theme={"background": "#000"},
            desired_rows=30,
        )
        assert config.font_size == 16
        assert config.font_family == "Courier"
        assert config.line_height == 1.2
        assert config.theme == {"background": "#000"}
        assert config.desired_rows == 30


class TestTerminalSize:
    """Test TerminalSize dataclass."""

    def test_default_values(self):
        """Test default size values."""
        size = TerminalSize(rows=24, cols=80, font_size=14)
        assert size.rows == 24
        assert size.cols == 80
        assert size.font_size == 14
        assert size.baseline_rows is None
        assert size.done is False

    def test_all_values(self):
        """Test with all values specified."""
        size = TerminalSize(
            rows=30,
            cols=120,
            font_size=12,
            baseline_rows=24,
            done=True,
        )
        assert size.rows == 30
        assert size.cols == 120
        assert size.font_size == 12
        assert size.baseline_rows == 24
        assert size.done is True


class TestConfigToDict:
    """Test _config_to_dict helper function."""

    def test_converts_config_to_dict(self):
        """Should convert TerminalConfig to JS-compatible dict."""
        config = TerminalConfig(
            font_size=14,
            font_family="Monaco",
            line_height=1.0,
            theme={"background": "#000"},
            desired_rows=30,
        )
        result = _config_to_dict(config)

        assert result["fontSize"] == 14
        assert result["fontFamily"] == "Monaco"
        assert result["lineHeight"] == 1.0
        assert result["theme"] == {"background": "#000"}
        assert result["desiredRows"] == 30

    def test_camelcase_keys(self):
        """Should use camelCase for JS compatibility."""
        config = TerminalConfig()
        result = _config_to_dict(config)

        # Keys should be camelCase for JavaScript
        assert "fontSize" in result
        assert "fontFamily" in result
        assert "lineHeight" in result
        assert "desiredRows" in result


class TestParseTerminalResult:
    """Test _parse_terminal_result helper function."""

    def test_parses_valid_result(self):
        """Should parse valid JS result into TerminalSize."""
        result = {
            "rows": 30,
            "cols": 120,
            "fontSize": 12,
        }
        size = _parse_terminal_result(result)

        assert size.rows == 30
        assert size.cols == 120
        assert size.font_size == 12

    def test_handles_optional_fields(self):
        """Should handle optional baseline_rows field."""
        result = {
            "rows": 30,
            "cols": 120,
            "fontSize": 12,
            "baselineRows": 24,
        }
        size = _parse_terminal_result(result)
        assert size.baseline_rows == 24

    def test_handles_done_field(self):
        """Should handle done field - note: _parse_terminal_result doesn't set done."""
        # _parse_terminal_result only extracts rows, cols, fontSize, baselineRows
        # The done field is handled separately in _fit_iteration
        result = {
            "rows": 30,
            "cols": 120,
            "fontSize": 12,
        }
        size = _parse_terminal_result(result)
        # Default done is False since _parse_terminal_result doesn't extract it
        assert size.done is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
