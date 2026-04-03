"""Parser for .demorec script files."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class Command:
    """A single command in the script."""

    name: str
    args: list[str] = field(default_factory=list)
    line_num: int = 0

    def __repr__(self):
        if self.args:
            return f"{self.name} {' '.join(repr(a) for a in self.args)}"
        return self.name


@dataclass
class Narration:
    """A narration directive."""

    mode: Literal["before", "during", "after"]
    text: str
    line_num: int = 0


@dataclass
class Segment:
    """A segment of commands in a single mode."""

    mode: Literal["terminal", "browser", "presentation"]
    session_name: str = "default"  # For terminal sessions (e.g., terminal:server)
    submode: str | None = None  # Tool-specific submode (e.g., "vim", "openhands")
    commands: list[Command] = field(default_factory=list)
    narrations: dict[int, Narration] = field(default_factory=dict)  # command_index -> narration
    # Terminal-specific settings
    size: Literal["large", "medium", "small", "tiny"] | None = None  # Display size preset
    rows: int | None = None  # Explicit row count (overrides size preset)
    # Presentation-specific settings
    presentation_file: str | None = None  # Path or URL to .md file
    presentation_theme: str | None = None  # Path, URL, or alias to CSS theme
    # Runtime field: populated by Runner with TimedNarration objects
    # Type is dict[int, "TimedNarration"] but avoiding import to prevent circular deps
    timed_narrations: dict = field(default_factory=dict)


@dataclass
class Plan:
    """The complete execution plan for a script."""

    output: Path = field(default_factory=lambda: Path("output.mp4"))
    width: int = 1280
    height: int = 720
    framerate: int = 30
    voice: str | None = None
    segments: list[Segment] = field(default_factory=list)


def parse_time(s: str) -> float:
    """Parse a time string like '2s' or '500ms' to seconds."""
    s = s.strip().lower()
    if s.endswith("ms"):
        return float(s[:-2]) / 1000
    elif s.endswith("s"):
        return float(s[:-1])
    elif s.endswith("m"):
        return float(s[:-1]) * 60
    else:
        return float(s)


def parse_string(s: str) -> str:
    """Parse a quoted string, handling escapes."""
    if not s:
        return s
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    # Handle escape sequences
    s = s.replace("\\n", "\n")
    s = s.replace("\\t", "\t")
    s = s.replace('\\"', '"')
    s = s.replace("\\'", "'")
    s = s.replace("\\\\", "\\")
    return s


class _Tokenizer:
    """Stateful tokenizer for parsing lines with quoted strings."""

    def __init__(self, line: str):
        self.line = line
        self.tokens: list[str] = []
        self.current = ""
        self.in_quotes = False
        self.quote_char: str | None = None
        self.i = 0

    def _handle_escape(self) -> bool:
        """Handle escape sequence. Returns True if processed."""
        if self.line[self.i] == "\\" and self.i + 1 < len(self.line):
            self.current += self.line[self.i : self.i + 2]
            self.i += 2
            return True
        return False

    def _close_quote(self):
        """Close current quoted string."""
        self.current += self.line[self.i]
        self.tokens.append(self.current)
        self.current = ""
        self.in_quotes = False

    def _open_quote(self, char: str):
        """Start a new quoted string."""
        if self.current:
            self.tokens.append(self.current)
        self.current = char
        self.in_quotes = True
        self.quote_char = char

    def _flush_token(self):
        """Flush current token if non-empty."""
        if self.current:
            self.tokens.append(self.current)
            self.current = ""

    def tokenize(self) -> list[str]:
        """Tokenize the line and return list of tokens."""
        while self.i < len(self.line):
            self._process_char(self.line[self.i])
            self.i += 1
        self._flush_token()
        return self.tokens

    def _process_char(self, c: str):
        """Process a single character."""
        if self.in_quotes:
            self._process_quoted_char(c)
        elif c in ('"', "'"):
            self._open_quote(c)
        elif c.isspace():
            self._flush_token()
        else:
            self.current += c

    def _process_quoted_char(self, c: str):
        """Process a character inside quotes."""
        if self._handle_escape():
            self.i -= 1  # Will be incremented by caller
        elif c == self.quote_char:
            self._close_quote()
        else:
            self.current += c


def tokenize_line(line: str) -> list[str]:
    """Split a line into tokens, respecting quoted strings."""
    return _Tokenizer(line).tokenize()


@dataclass
class _ParseContext:
    """Mutable parsing state."""

    plan: Plan
    current_segment: Segment | None = None
    pending_narration: Narration | None = None
    in_settings_mode: bool = False  # True after @mode until blank line or ---


def _parse_comment(line: str, line_num: int, ctx: _ParseContext) -> bool:
    """Parse a comment line for directives. Returns True if line was handled."""
    narrate_match = re.match(r"#\s*@narrate:(before|during|after)\s+(.+)", line)
    if narrate_match:
        mode = narrate_match.group(1)
        text = parse_string(narrate_match.group(2).strip())
        ctx.pending_narration = Narration(mode=mode, text=text, line_num=line_num)
        return True

    voice_match = re.match(r"#\s*@voice\s+(\S+)", line)
    if voice_match:
        ctx.plan.voice = voice_match.group(1)
        return True

    return True  # Regular comment - skip


def _handle_set_directive(args: list[str], line_num: int, ctx: _ParseContext):
    """Handle the Set directive for plan settings."""
    if len(args) < 2:
        return
    key, val = args[0].lower(), args[1]
    if not _try_set_plan_attr(key, val, ctx.plan):
        _handle_set_theme(val, line_num, ctx)


def _try_set_plan_attr(key: str, val: str, plan: Plan) -> bool:
    """Try to set a plan attribute. Returns True if handled."""
    setters = {"width": int, "height": int, "framerate": int}
    if key in setters:
        setattr(plan, key, setters[key](val))
        return True
    return False


def _handle_set_theme(val: str, line_num: int, ctx: _ParseContext):
    """Handle Set Theme for current segment."""
    if not ctx.current_segment:
        return
    if ctx.current_segment.mode == "presentation":
        ctx.current_segment.presentation_theme = val
    else:
        ctx.current_segment.commands.append(Command("SetTheme", [val], line_num))


def _handle_mode_switch(args: list[str], ctx: _ParseContext):
    """Handle @mode directive to switch recording modes."""
    if not args:
        return
    mode, session_name, submode = _parse_mode_spec(args[0].lower())
    segment = _create_mode_segment(mode, session_name, submode, args)
    if segment:
        ctx.current_segment = segment
        ctx.plan.segments.append(segment)
        ctx.in_settings_mode = True  # Enter settings mode after @mode


# Known terminal sub-modes for tool-specific primitives
TERMINAL_SUBMODES = {"vim", "openhands"}

# Known segment settings (parsed after @mode, before commands)
SEGMENT_SETTINGS = {"rows", "size", "theme", "name"}


def _parse_mode_spec(mode_spec: str) -> tuple[str, str, str | None]:
    """Parse mode spec into (mode, session_name, submode).

    The colon after mode now always indicates a submode:
    - 'terminal' -> ('terminal', 'default', None)
    - 'terminal:vim' -> ('terminal', 'default', 'vim')
    - 'terminal:openhands' -> ('terminal', 'default', 'openhands')

    Session names are now specified via the 'name' setting after @mode.
    """
    if ":" not in mode_spec:
        return mode_spec, "default", None

    mode, submode = mode_spec.split(":", 1)
    return mode, "default", submode


VALID_MODES = {"terminal", "browser", "presentation"}


def _create_mode_segment(
    mode: str, session_name: str, submode: str | None, args: list[str]
) -> Segment | None:
    """Create a segment for the given mode."""
    if mode in ("terminal", "browser"):
        return Segment(mode=mode, session_name=session_name, submode=submode)
    if mode == "presentation":
        file_path = parse_string(args[1]) if len(args) > 1 else None
        return Segment(mode="presentation", presentation_file=file_path)
    if mode not in VALID_MODES:
        valid = ", ".join(sorted(VALID_MODES))
        logger.warning("Unknown mode '%s' - ignoring. Valid modes: %s", mode, valid)
    return None


def _validate_session_name(name: str) -> None:
    """Validate session name is a valid identifier."""
    if not name:
        raise ValueError("Session name cannot be empty")
    if not name.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"Invalid session name: {name!r} (use alphanumeric, dash, underscore)")


def _handle_terminal_directive(directive: str, args: list[str], ctx: _ParseContext) -> bool:
    """Handle @terminal:size and @terminal:rows directives."""
    if directive == "size" and args:
        return _handle_size_directive(args[0].lower(), ctx)
    if directive == "rows" and args:
        return _handle_rows_directive(args[0], ctx)
    return False


def _handle_size_directive(size: str, ctx: _ParseContext) -> bool:
    """Handle @terminal:size preset directive."""
    if size not in ("large", "medium", "small", "tiny"):
        return True
    _set_terminal_attr(ctx, "size", size)
    return True


def _handle_rows_directive(rows_str: str, ctx: _ParseContext) -> bool:
    """Handle @terminal:rows directive."""
    try:
        rows = int(rows_str)
        if 10 <= rows <= 100:
            _set_terminal_attr(ctx, "rows", rows)
    except ValueError:
        pass
    return True


def _set_terminal_attr(ctx: _ParseContext, attr: str, value):
    """Set attribute on current terminal segment, creating one if needed."""
    if ctx.current_segment and ctx.current_segment.mode == "terminal":
        setattr(ctx.current_segment, attr, value)
    elif ctx.current_segment is None:
        ctx.current_segment = Segment(mode="terminal", **{attr: value})
        ctx.plan.segments.append(ctx.current_segment)


def _ensure_segment(ctx: _ParseContext):
    """Ensure there's an active segment, defaulting to terminal."""
    if ctx.current_segment is None:
        ctx.current_segment = Segment(mode="terminal")
        ctx.plan.segments.append(ctx.current_segment)


def _add_command(name: str, args: list[str], line_num: int, ctx: _ParseContext):
    """Add a command to the current segment."""
    _ensure_segment(ctx)
    cmd = Command(name=name, args=args, line_num=line_num)
    cmd_index = len(ctx.current_segment.commands)
    ctx.current_segment.commands.append(cmd)

    if ctx.pending_narration:
        ctx.current_segment.narrations[cmd_index] = ctx.pending_narration
        ctx.pending_narration = None


def parse_script(path: Path) -> Plan:
    """Parse a .demorec script file into an execution plan."""
    ctx = _ParseContext(plan=Plan())

    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            _parse_line(line.strip(), line_num, ctx)

    return ctx.plan


def _parse_line(line: str, line_num: int, ctx: _ParseContext):
    """Parse a single line from the script."""
    if _handle_blank_or_delimiter(line, ctx):
        return
    if line.startswith("#"):
        _parse_comment(line, line_num, ctx)
        return
    tokens = tokenize_line(line)
    if tokens:
        _dispatch_command(tokens, line_num, ctx)


def _handle_blank_or_delimiter(line: str, ctx: _ParseContext) -> bool:
    """Handle blank lines and --- delimiter. Returns True if handled."""
    if not line:
        if ctx.in_settings_mode:
            ctx.in_settings_mode = False
        return True
    if line == "---":
        ctx.in_settings_mode = False
        return True
    return False


def _dispatch_command(tokens: list[str], line_num: int, ctx: _ParseContext):
    """Dispatch a parsed command to the appropriate handler."""
    cmd_name, cmd_args = tokens[0], [parse_string(t) for t in tokens[1:]]

    if _handle_global_directive(cmd_name, cmd_args, line_num, ctx):
        return
    if _handle_settings_mode(cmd_name, cmd_args, line_num, ctx):
        return
    _warn_if_misplaced_setting(cmd_name, line_num, ctx)
    if _handle_legacy_terminal_directive(cmd_name, cmd_args, ctx):
        return
    _add_command(cmd_name, cmd_args, line_num, ctx)


def _handle_global_directive(name: str, args: list[str], line_num: int, ctx: _ParseContext) -> bool:
    """Handle global directives (Output, Set, @mode). Returns True if handled."""
    if name == "Output" and args:
        ctx.plan.output = Path(args[0])
        return True
    if name == "Set":
        _handle_set_directive(args, line_num, ctx)
        return True
    if name == "@mode":
        _handle_mode_switch(args, ctx)
        return True
    return False


def _handle_settings_mode(name: str, args: list[str], line_num: int, ctx: _ParseContext) -> bool:
    """Handle settings mode parsing. Returns True if handled as setting."""
    if not ctx.in_settings_mode:
        return False
    if _handle_segment_setting(name.lower(), args, line_num, ctx):
        return True
    ctx.in_settings_mode = False  # Not a setting - exit settings mode
    return False


def _handle_legacy_terminal_directive(name: str, args: list[str], ctx: _ParseContext) -> bool:
    """Handle legacy @terminal: directives. Returns True if handled."""
    if not name.startswith("@terminal:"):
        return False
    directive = name.split(":", 1)[1].lower()
    _handle_terminal_directive(directive, args, ctx)
    return True


def _handle_segment_setting(name: str, args: list[str], line_num: int, ctx: _ParseContext) -> bool:
    """Handle a segment setting. Returns True if handled."""
    if name not in SEGMENT_SETTINGS or not ctx.current_segment:
        return False
    _apply_segment_setting(name, args, line_num, ctx)
    return True


def _apply_segment_setting(name: str, args: list[str], line_num: int, ctx: _ParseContext):
    """Apply a segment setting to the current segment."""
    if not args:
        return
    if name == "rows":
        _apply_rows_setting(args[0], ctx)
    elif name == "size":
        _apply_size_setting(args[0].lower(), ctx)
    elif name == "theme":
        ctx.current_segment.commands.append(Command("SetTheme", args, line_num))
    elif name == "name":
        ctx.current_segment.session_name = args[0]


def _apply_rows_setting(rows_str: str, ctx: _ParseContext):
    """Apply rows setting to current segment."""
    try:
        rows = int(rows_str)
        if 10 <= rows <= 100 and ctx.current_segment:
            ctx.current_segment.rows = rows
    except ValueError:
        pass


def _apply_size_setting(size: str, ctx: _ParseContext):
    """Apply size preset to current segment."""
    if size in ("large", "medium", "small", "tiny") and ctx.current_segment:
        ctx.current_segment.size = size


def _warn_if_misplaced_setting(cmd_name: str, line_num: int, ctx: _ParseContext):
    """Warn if a setting name appears after commands have started."""
    if cmd_name.lower() not in SEGMENT_SETTINGS:
        return
    if not ctx.current_segment:
        return
    if not ctx.current_segment.commands:
        return  # No commands yet, might still be valid

    logger.warning(
        "Line %d: '%s' looks like a setting but appears after commands. "
        "Settings must come immediately after @mode, before the first blank line or ---.",
        line_num,
        cmd_name,
    )
