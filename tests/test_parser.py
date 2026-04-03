"""Unit tests for parser module.

Tests cover:
- Command, Narration, Segment, Plan dataclasses
- parse_time
- parse_string
- _Tokenizer and tokenize_line
- _ParseContext
- _parse_comment
- _handle_set_directive
- _handle_mode_switch
- _handle_terminal_directive
- parse_script
- _parse_line
- _dispatch_command
"""

import tempfile
from pathlib import Path

import pytest

from demorec.parser import (
    Command,
    Narration,
    Plan,
    Segment,
    _ParseContext,
    _Tokenizer,
    _add_command,
    _dispatch_command,
    _ensure_segment,
    _handle_mode_switch,
    _handle_offscreen_directive,
    _handle_onscreen_directive,
    _handle_rows_directive,
    _handle_set_directive,
    _handle_size_directive,
    _handle_terminal_directive,
    _parse_comment,
    _parse_line,
    _set_terminal_attr,
    parse_script,
    parse_string,
    parse_time,
    tokenize_line,
)


class TestCommand:
    """Test Command dataclass."""

    def test_command_creation(self):
        """Should create command with name and args."""
        cmd = Command("Type", ["hello"], 10)
        assert cmd.name == "Type"
        assert cmd.args == ["hello"]
        assert cmd.line_num == 10

    def test_command_defaults(self):
        """Should have default empty args and line_num 0."""
        cmd = Command("Enter")
        assert cmd.args == []
        assert cmd.line_num == 0

    def test_command_repr_with_args(self):
        """Should repr with args."""
        cmd = Command("Type", ["hello"])
        assert repr(cmd) == "Type 'hello'"

    def test_command_repr_without_args(self):
        """Should repr without args."""
        cmd = Command("Enter")
        assert repr(cmd) == "Enter"


class TestNarration:
    """Test Narration dataclass."""

    def test_narration_creation(self):
        """Should create narration with mode and text."""
        narration = Narration(mode="before", text="Hello world", line_num=5)
        assert narration.mode == "before"
        assert narration.text == "Hello world"
        assert narration.line_num == 5

    def test_narration_modes(self):
        """Should support before, during, after modes."""
        for mode in ["before", "during", "after"]:
            narration = Narration(mode=mode, text="test")
            assert narration.mode == mode


class TestSegment:
    """Test Segment dataclass."""

    def test_segment_creation(self):
        """Should create segment with mode."""
        segment = Segment(mode="terminal")
        assert segment.mode == "terminal"
        assert segment.commands == []
        assert segment.narrations == {}
        assert segment.size is None
        assert segment.rows is None

    def test_segment_with_commands(self):
        """Should store commands."""
        segment = Segment(
            mode="terminal",
            commands=[Command("Type", ["hello"]), Command("Enter")],
        )
        assert len(segment.commands) == 2

    def test_segment_with_size(self):
        """Should store size preset."""
        segment = Segment(mode="terminal", size="large")
        assert segment.size == "large"

    def test_segment_with_rows(self):
        """Should store explicit rows."""
        segment = Segment(mode="terminal", rows=30)
        assert segment.rows == 30


class TestPlan:
    """Test Plan dataclass."""

    def test_plan_defaults(self):
        """Should have sensible defaults."""
        plan = Plan()
        assert plan.output == Path("output.mp4")
        assert plan.width == 1280
        assert plan.height == 720
        assert plan.framerate == 30
        assert plan.voice is None
        assert plan.segments == []

    def test_plan_custom_values(self):
        """Should accept custom values."""
        plan = Plan(
            output=Path("test.mp4"),
            width=1920,
            height=1080,
            framerate=60,
            voice="edge:jenny",
        )
        assert plan.output == Path("test.mp4")
        assert plan.width == 1920
        assert plan.framerate == 60
        assert plan.voice == "edge:jenny"


class TestParseTime:
    """Test parse_time function."""

    def test_parse_seconds(self):
        """Should parse seconds."""
        assert parse_time("2s") == 2.0
        assert parse_time("0.5s") == 0.5
        assert parse_time("10s") == 10.0

    def test_parse_milliseconds(self):
        """Should parse milliseconds."""
        assert parse_time("500ms") == 0.5
        assert parse_time("1000ms") == 1.0
        assert parse_time("100ms") == 0.1

    def test_parse_minutes(self):
        """Should parse minutes."""
        assert parse_time("1m") == 60.0
        assert parse_time("2m") == 120.0

    def test_parse_plain_number(self):
        """Should parse plain number as seconds."""
        assert parse_time("2") == 2.0
        assert parse_time("0.5") == 0.5

    def test_parse_with_whitespace(self):
        """Should handle whitespace."""
        assert parse_time(" 2s ") == 2.0
        assert parse_time("  500ms  ") == 0.5


class TestParseString:
    """Test parse_string function."""

    def test_parse_double_quoted(self):
        """Should parse double-quoted string."""
        assert parse_string('"hello"') == "hello"

    def test_parse_single_quoted(self):
        """Should parse single-quoted string."""
        assert parse_string("'hello'") == "hello"

    def test_parse_unquoted(self):
        """Should return unquoted string as-is."""
        assert parse_string("hello") == "hello"

    def test_parse_empty(self):
        """Should handle empty string."""
        assert parse_string("") == ""

    def test_parse_escape_newline(self):
        """Should handle \\n escape."""
        assert parse_string('"hello\\nworld"') == "hello\nworld"

    def test_parse_escape_tab(self):
        """Should handle \\t escape."""
        assert parse_string('"hello\\tworld"') == "hello\tworld"

    def test_parse_escape_quote(self):
        """Should handle escaped quotes."""
        assert parse_string('"he said \\"hi\\""') == 'he said "hi"'
        assert parse_string("'it\\'s'") == "it's"

    def test_parse_escape_backslash(self):
        """Should handle escaped backslash."""
        # Test simple backslash escape
        result = parse_string('"hello\\\\world"')
        # After quote removal: hello\\world
        # After \\\\ -> \\ replacement: hello\world
        assert result == "hello\\world"


class TestTokenizer:
    """Test _Tokenizer class."""

    def test_tokenize_simple_words(self):
        """Should tokenize space-separated words."""
        tokens = _Tokenizer("hello world").tokenize()
        assert tokens == ["hello", "world"]

    def test_tokenize_quoted_string(self):
        """Should keep quoted strings together."""
        tokens = _Tokenizer('Type "hello world"').tokenize()
        assert tokens == ["Type", '"hello world"']

    def test_tokenize_multiple_args(self):
        """Should handle multiple arguments."""
        tokens = _Tokenizer("Set Width 1280").tokenize()
        assert tokens == ["Set", "Width", "1280"]

    def test_tokenize_escape_in_quotes(self):
        """Should handle escapes inside quotes."""
        tokens = _Tokenizer('Type "hello\\"world"').tokenize()
        assert tokens == ["Type", '"hello\\"world"']

    def test_tokenize_empty(self):
        """Should handle empty string."""
        tokens = _Tokenizer("").tokenize()
        assert tokens == []


class TestTokenizeLine:
    """Test tokenize_line function."""

    def test_tokenize_line_basic(self):
        """Should tokenize basic line."""
        tokens = tokenize_line('Type "hello"')
        assert tokens == ["Type", '"hello"']

    def test_tokenize_line_single_quotes(self):
        """Should handle single quotes."""
        tokens = tokenize_line("Type 'hello'")
        assert tokens == ["Type", "'hello'"]


class TestParseContext:
    """Test _ParseContext class."""

    def test_parse_context_defaults(self):
        """Should initialize with plan and no segment."""
        ctx = _ParseContext(plan=Plan())
        assert ctx.plan is not None
        assert ctx.current_segment is None
        assert ctx.pending_narration is None


class TestParseComment:
    """Test _parse_comment function."""

    def test_parse_narrate_before(self):
        """Should parse @narrate:before directive."""
        ctx = _ParseContext(plan=Plan())
        _parse_comment("# @narrate:before Say something", 5, ctx)
        assert ctx.pending_narration is not None
        assert ctx.pending_narration.mode == "before"
        assert ctx.pending_narration.text == "Say something"

    def test_parse_narrate_after(self):
        """Should parse @narrate:after directive."""
        ctx = _ParseContext(plan=Plan())
        _parse_comment("# @narrate:after Done!", 5, ctx)
        assert ctx.pending_narration.mode == "after"

    def test_parse_narrate_during(self):
        """Should parse @narrate:during directive."""
        ctx = _ParseContext(plan=Plan())
        _parse_comment("# @narrate:during While this runs", 5, ctx)
        assert ctx.pending_narration.mode == "during"

    def test_parse_voice_directive(self):
        """Should parse @voice directive."""
        ctx = _ParseContext(plan=Plan())
        _parse_comment("# @voice edge:jenny", 5, ctx)
        assert ctx.plan.voice == "edge:jenny"

    def test_regular_comment_ignored(self):
        """Should ignore regular comments."""
        ctx = _ParseContext(plan=Plan())
        _parse_comment("# This is just a comment", 5, ctx)
        assert ctx.pending_narration is None


class TestHandleSetDirective:
    """Test _handle_set_directive function."""

    def test_set_width(self):
        """Should set width."""
        ctx = _ParseContext(plan=Plan())
        _handle_set_directive(["Width", "1920"], 1, ctx)
        assert ctx.plan.width == 1920

    def test_set_height(self):
        """Should set height."""
        ctx = _ParseContext(plan=Plan())
        _handle_set_directive(["Height", "1080"], 1, ctx)
        assert ctx.plan.height == 1080

    def test_set_framerate(self):
        """Should set framerate."""
        ctx = _ParseContext(plan=Plan())
        _handle_set_directive(["Framerate", "60"], 1, ctx)
        assert ctx.plan.framerate == 60

    def test_set_theme(self):
        """Should set theme when segment exists."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        _handle_set_directive(["Theme", "dark"], 1, ctx)
        assert len(ctx.current_segment.commands) == 1
        assert ctx.current_segment.commands[0].name == "SetTheme"

    def test_set_insufficient_args(self):
        """Should handle insufficient args."""
        ctx = _ParseContext(plan=Plan())
        _handle_set_directive(["Width"], 1, ctx)  # Should not crash
        assert ctx.plan.width == 1280  # Default unchanged


class TestHandleModeSwitch:
    """Test _handle_mode_switch function."""

    def test_switch_to_terminal(self):
        """Should switch to terminal mode."""
        ctx = _ParseContext(plan=Plan())
        _handle_mode_switch(["terminal"], ctx)
        assert ctx.current_segment is not None
        assert ctx.current_segment.mode == "terminal"
        assert len(ctx.plan.segments) == 1

    def test_switch_to_browser(self):
        """Should switch to browser mode."""
        ctx = _ParseContext(plan=Plan())
        _handle_mode_switch(["browser"], ctx)
        assert ctx.current_segment.mode == "browser"

    def test_invalid_mode_ignored(self):
        """Should ignore invalid modes."""
        ctx = _ParseContext(plan=Plan())
        _handle_mode_switch(["invalid"], ctx)
        assert ctx.current_segment is None

    def test_terminal_with_named_session(self):
        """Should parse terminal:session_name syntax."""
        ctx = _ParseContext(plan=Plan())
        _handle_mode_switch(["terminal:server"], ctx)
        assert ctx.current_segment.mode == "terminal"
        assert ctx.current_segment.session_name == "server"

    def test_terminal_with_default_session(self):
        """Should use 'default' session when not specified."""
        ctx = _ParseContext(plan=Plan())
        _handle_mode_switch(["terminal"], ctx)
        assert ctx.current_segment.session_name == "default"

    def test_terminal_session_name_with_underscores(self):
        """Should accept session names with underscores."""
        ctx = _ParseContext(plan=Plan())
        _handle_mode_switch(["terminal:my_session"], ctx)
        assert ctx.current_segment.session_name == "my_session"

    def test_terminal_session_name_with_dashes(self):
        """Should accept session names with dashes."""
        ctx = _ParseContext(plan=Plan())
        _handle_mode_switch(["terminal:my-session"], ctx)
        assert ctx.current_segment.session_name == "my-session"

    def test_terminal_invalid_session_name_with_space(self):
        """Should reject session names with invalid characters."""
        ctx = _ParseContext(plan=Plan())
        with pytest.raises(ValueError, match="Invalid session name"):
            _handle_mode_switch(["terminal:my session"], ctx)

    def test_terminal_invalid_session_name_with_emoji(self):
        """Should reject session names with emoji."""
        ctx = _ParseContext(plan=Plan())
        with pytest.raises(ValueError, match="Invalid session name"):
            _handle_mode_switch(["terminal:💩"], ctx)

    def test_terminal_empty_session_name(self):
        """Should reject empty session names."""
        ctx = _ParseContext(plan=Plan())
        with pytest.raises(ValueError, match="cannot be empty"):
            _handle_mode_switch(["terminal:"], ctx)


class TestHandleTerminalDirective:
    """Test _handle_terminal_directive function."""

    def test_handle_size_directive(self):
        """Should handle @terminal:size directive."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        result = _handle_terminal_directive("size", ["large"], ctx)
        assert result is True
        assert ctx.current_segment.size == "large"

    def test_handle_rows_directive(self):
        """Should handle @terminal:rows directive."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        result = _handle_terminal_directive("rows", ["30"], ctx)
        assert result is True
        assert ctx.current_segment.rows == 30

    def test_unknown_directive(self):
        """Should return False for unknown directive."""
        ctx = _ParseContext(plan=Plan())
        result = _handle_terminal_directive("unknown", ["value"], ctx)
        assert result is False


class TestHandleSizeDirective:
    """Test _handle_size_directive function."""

    def test_valid_sizes(self):
        """Should accept valid size presets."""
        for size in ["large", "medium", "small", "tiny"]:
            ctx = _ParseContext(plan=Plan())
            ctx.current_segment = Segment(mode="terminal")
            _handle_size_directive(size, ctx)
            assert ctx.current_segment.size == size

    def test_invalid_size(self):
        """Should ignore invalid size."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        _handle_size_directive("huge", ctx)
        assert ctx.current_segment.size is None


class TestHandleRowsDirective:
    """Test _handle_rows_directive function."""

    def test_valid_rows(self):
        """Should accept valid row counts."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        _handle_rows_directive("30", ctx)
        assert ctx.current_segment.rows == 30

    def test_rows_min_boundary(self):
        """Should accept minimum rows (10)."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        _handle_rows_directive("10", ctx)
        assert ctx.current_segment.rows == 10

    def test_rows_max_boundary(self):
        """Should accept maximum rows (100)."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        _handle_rows_directive("100", ctx)
        assert ctx.current_segment.rows == 100

    def test_rows_below_min_ignored(self):
        """Should ignore rows below minimum."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        _handle_rows_directive("5", ctx)
        assert ctx.current_segment.rows is None

    def test_rows_above_max_ignored(self):
        """Should ignore rows above maximum."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        _handle_rows_directive("150", ctx)
        assert ctx.current_segment.rows is None

    def test_invalid_rows_ignored(self):
        """Should ignore non-numeric rows."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        _handle_rows_directive("abc", ctx)
        assert ctx.current_segment.rows is None


class TestSetTerminalAttr:
    """Test _set_terminal_attr function."""

    def test_set_attr_on_existing_segment(self):
        """Should set attribute on existing terminal segment."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        ctx.plan.segments.append(ctx.current_segment)
        _set_terminal_attr(ctx, "rows", 30)
        assert ctx.current_segment.rows == 30

    def test_creates_segment_if_none(self):
        """Should create segment if none exists."""
        ctx = _ParseContext(plan=Plan())
        _set_terminal_attr(ctx, "rows", 30)
        assert ctx.current_segment is not None
        assert ctx.current_segment.mode == "terminal"
        assert ctx.current_segment.rows == 30

    def test_ignores_browser_segment(self):
        """Should not set on browser segment."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="browser")
        ctx.plan.segments.append(ctx.current_segment)
        original_segment = ctx.current_segment
        _set_terminal_attr(ctx, "rows", 30)
        # Should not modify browser segment
        assert not hasattr(original_segment, "rows") or original_segment.rows is None


class TestEnsureSegment:
    """Test _ensure_segment function."""

    def test_creates_terminal_segment(self):
        """Should create terminal segment if none exists."""
        ctx = _ParseContext(plan=Plan())
        _ensure_segment(ctx)
        assert ctx.current_segment is not None
        assert ctx.current_segment.mode == "terminal"
        assert len(ctx.plan.segments) == 1

    def test_does_nothing_if_segment_exists(self):
        """Should not create if segment exists."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="browser")
        ctx.plan.segments.append(ctx.current_segment)
        _ensure_segment(ctx)
        assert len(ctx.plan.segments) == 1
        assert ctx.current_segment.mode == "browser"


class TestAddCommand:
    """Test _add_command function."""

    def test_adds_command_to_segment(self):
        """Should add command to current segment."""
        ctx = _ParseContext(plan=Plan())
        _add_command("Type", ["hello"], 1, ctx)
        assert len(ctx.current_segment.commands) == 1
        assert ctx.current_segment.commands[0].name == "Type"

    def test_attaches_pending_narration(self):
        """Should attach pending narration to command."""
        ctx = _ParseContext(plan=Plan())
        ctx.pending_narration = Narration(mode="before", text="test", line_num=1)
        _add_command("Type", ["hello"], 2, ctx)
        assert 0 in ctx.current_segment.narrations
        assert ctx.pending_narration is None


class TestParseLine:
    """Test _parse_line function."""

    def test_skips_empty_line(self):
        """Should skip empty lines."""
        ctx = _ParseContext(plan=Plan())
        _parse_line("", 1, ctx)
        assert ctx.current_segment is None

    def test_handles_comment(self):
        """Should handle comment lines."""
        ctx = _ParseContext(plan=Plan())
        _parse_line("# @voice edge:jenny", 1, ctx)
        assert ctx.plan.voice == "edge:jenny"

    def test_handles_command(self):
        """Should handle command lines."""
        ctx = _ParseContext(plan=Plan())
        _parse_line('Type "hello"', 1, ctx)
        assert ctx.current_segment is not None
        assert len(ctx.current_segment.commands) == 1


class TestDispatchCommand:
    """Test _dispatch_command function."""

    def test_dispatch_output(self):
        """Should handle Output command."""
        ctx = _ParseContext(plan=Plan())
        _dispatch_command(["Output", "test.mp4"], 1, ctx)
        assert ctx.plan.output == Path("test.mp4")

    def test_dispatch_set(self):
        """Should handle Set command."""
        ctx = _ParseContext(plan=Plan())
        _dispatch_command(["Set", "Width", "1920"], 1, ctx)
        assert ctx.plan.width == 1920

    def test_dispatch_mode(self):
        """Should handle @mode command."""
        ctx = _ParseContext(plan=Plan())
        _dispatch_command(["@mode", "terminal"], 1, ctx)
        assert ctx.current_segment is not None
        assert ctx.current_segment.mode == "terminal"

    def test_dispatch_terminal_directive(self):
        """Should handle @terminal: directives."""
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        ctx.plan.segments.append(ctx.current_segment)
        _dispatch_command(["@terminal:rows", "30"], 1, ctx)
        assert ctx.current_segment.rows == 30

    def test_dispatch_regular_command(self):
        """Should add regular commands."""
        ctx = _ParseContext(plan=Plan())
        _dispatch_command(["Type", '"hello"'], 1, ctx)
        assert ctx.current_segment.commands[0].name == "Type"


class TestParseScript:
    """Test parse_script function."""

    def test_parse_basic_script(self):
        """Should parse basic script file."""
        script = """
Output test.mp4
Set Width 1920
Set Height 1080

@mode terminal
Type "hello"
Enter
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = parse_script(path)
            assert plan.output == Path("test.mp4")
            assert plan.width == 1920
            assert plan.height == 1080
            assert len(plan.segments) == 1
            assert len(plan.segments[0].commands) == 2
        finally:
            path.unlink()

    def test_parse_with_narration(self):
        """Should parse script with narration."""
        script = """
@mode terminal
# @narrate:before Say hello
Type "hello"
Enter
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = parse_script(path)
            assert 0 in plan.segments[0].narrations
            assert plan.segments[0].narrations[0].mode == "before"
        finally:
            path.unlink()

    def test_parse_multiple_segments(self):
        """Should parse multiple mode segments."""
        script = """
@mode terminal
Type "hello"

@mode browser
Navigate "https://example.com"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = parse_script(path)
            assert len(plan.segments) == 2
            assert plan.segments[0].mode == "terminal"
            assert plan.segments[1].mode == "browser"
        finally:
            path.unlink()

    def test_parse_terminal_rows(self):
        """Should parse terminal rows directive."""
        script = """
@mode terminal
@terminal:rows 30
Type "hello"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = parse_script(path)
            assert plan.segments[0].rows == 30
        finally:
            path.unlink()

    def test_parse_offscreen_segment(self):
        """Should parse offscreen directive and mark segments."""
        script = """
@offscreen
@mode terminal
Type "setup"

@onscreen
@mode terminal
Type "visible"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = parse_script(path)
            assert len(plan.segments) == 2
            assert plan.segments[0].offscreen is True
            assert plan.segments[1].offscreen is False
        finally:
            path.unlink()

    def test_parse_offscreen_before_mode(self):
        """Should mark segment created after offscreen directive."""
        script = """
@offscreen
Type "setup"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = parse_script(path)
            assert len(plan.segments) == 1
            assert plan.segments[0].offscreen is True
        finally:
            path.unlink()

    def test_parse_offscreen_browser(self):
        """Should support offscreen browser segments."""
        script = """
@offscreen
@mode browser
Navigate "http://localhost"
Sleep 2s

@onscreen
@mode browser
Click "#button"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".demorec", delete=False) as f:
            f.write(script)
            path = Path(f.name)

        try:
            plan = parse_script(path)
            assert len(plan.segments) == 2
            assert plan.segments[0].mode == "browser"
            assert plan.segments[0].offscreen is True
            assert plan.segments[1].mode == "browser"
            assert plan.segments[1].offscreen is False
        finally:
            path.unlink()


class TestOffscreenDirectives:
    """Test @offscreen and @onscreen directives."""

    def test_offscreen_sets_context_flag(self):
        """Should set offscreen flag in context."""
        ctx = _ParseContext(plan=Plan())
        assert ctx.offscreen is False
        _handle_offscreen_directive(ctx)
        assert ctx.offscreen is True

    def test_onscreen_clears_context_flag(self):
        """Should clear offscreen flag in context."""
        ctx = _ParseContext(plan=Plan())
        ctx.offscreen = True
        _handle_onscreen_directive(ctx)
        assert ctx.offscreen is False

    def test_offscreen_does_not_update_current_segment(self):
        """Should NOT update current segment's offscreen flag.

        The offscreen directive applies to segments created AFTER it,
        not to the segment that was already being recorded.
        """
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal")
        _handle_offscreen_directive(ctx)
        # Current segment should remain onscreen (False)
        assert ctx.current_segment.offscreen is False
        # But context flag should be True for new segments
        assert ctx.offscreen is True

    def test_onscreen_does_not_update_current_segment(self):
        """Should NOT update current segment's offscreen flag.

        The onscreen directive applies to segments created AFTER it.
        """
        ctx = _ParseContext(plan=Plan())
        ctx.current_segment = Segment(mode="terminal", offscreen=True)
        _handle_onscreen_directive(ctx)
        # Current segment should remain offscreen (True)
        assert ctx.current_segment.offscreen is True
        # But context flag should be False for new segments
        assert ctx.offscreen is False

    def test_mode_switch_inherits_offscreen(self):
        """Should apply offscreen context to new segments."""
        ctx = _ParseContext(plan=Plan())
        _handle_offscreen_directive(ctx)
        _handle_mode_switch(["terminal"], ctx)
        assert ctx.current_segment.offscreen is True

    def test_mode_switch_after_onscreen(self):
        """Should not be offscreen after @onscreen."""
        ctx = _ParseContext(plan=Plan())
        _handle_offscreen_directive(ctx)
        _handle_onscreen_directive(ctx)
        _handle_mode_switch(["terminal"], ctx)
        assert ctx.current_segment.offscreen is False

    def test_dispatch_offscreen(self):
        """Should dispatch @offscreen command."""
        ctx = _ParseContext(plan=Plan())
        _dispatch_command(["@offscreen"], 1, ctx)
        assert ctx.offscreen is True

    def test_dispatch_onscreen(self):
        """Should dispatch @onscreen command."""
        ctx = _ParseContext(plan=Plan())
        ctx.offscreen = True
        _dispatch_command(["@onscreen"], 1, ctx)
        assert ctx.offscreen is False


class TestSegmentOffscreen:
    """Test Segment offscreen field."""

    def test_segment_offscreen_default(self):
        """Should default to False (onscreen)."""
        segment = Segment(mode="terminal")
        assert segment.offscreen is False

    def test_segment_offscreen_explicit(self):
        """Should accept explicit offscreen value."""
        segment = Segment(mode="terminal", offscreen=True)
        assert segment.offscreen is True

    def test_ensure_segment_inherits_offscreen(self):
        """Should create segment with context offscreen state."""
        ctx = _ParseContext(plan=Plan())
        ctx.offscreen = True
        _ensure_segment(ctx)
        assert ctx.current_segment.offscreen is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
