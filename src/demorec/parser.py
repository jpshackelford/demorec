"""Parser for .demorec script files."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


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

    mode: Literal["terminal", "browser"]
    commands: list[Command] = field(default_factory=list)
    narrations: dict[int, Narration] = field(default_factory=dict)  # command_index -> narration
    # Terminal-specific settings
    size: Literal["large", "medium", "small", "tiny"] | None = None  # Display size preset
    rows: int | None = None  # Explicit row count (overrides size preset)


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
    setters = {
        "width": lambda: setattr(ctx.plan, "width", int(val)),
        "height": lambda: setattr(ctx.plan, "height", int(val)),
        "framerate": lambda: setattr(ctx.plan, "framerate", int(val)),
    }
    if key in setters:
        setters[key]()
    elif key == "theme" and ctx.current_segment:
        ctx.current_segment.commands.append(Command("SetTheme", [val], line_num))


def _handle_mode_switch(args: list[str], ctx: _ParseContext):
    """Handle @mode directive to switch recording modes."""
    if args and args[0].lower() in ("terminal", "browser"):
        ctx.current_segment = Segment(mode=args[0].lower())
        ctx.plan.segments.append(ctx.current_segment)


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
    if not line:
        return
    if line.startswith("#"):
        _parse_comment(line, line_num, ctx)
        return

    tokens = tokenize_line(line)
    if tokens:
        _dispatch_command(tokens, line_num, ctx)


def _dispatch_command(tokens: list[str], line_num: int, ctx: _ParseContext):
    """Dispatch a parsed command to the appropriate handler."""
    cmd_name, cmd_args = tokens[0], [parse_string(t) for t in tokens[1:]]

    if cmd_name == "Output" and cmd_args:
        ctx.plan.output = Path(cmd_args[0])
    elif cmd_name == "Set":
        _handle_set_directive(cmd_args, line_num, ctx)
    elif cmd_name == "@mode":
        _handle_mode_switch(cmd_args, ctx)
    elif cmd_name.startswith("@terminal:"):
        directive = cmd_name.split(":", 1)[1].lower()
        _handle_terminal_directive(directive, cmd_args, ctx)
    else:
        _add_command(cmd_name, cmd_args, line_num, ctx)
