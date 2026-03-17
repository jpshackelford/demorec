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


def tokenize_line(line: str) -> list[str]:
    """Split a line into tokens, respecting quoted strings."""
    tokens = []
    current = ""
    in_quotes = False
    quote_char = None
    
    i = 0
    while i < len(line):
        c = line[i]
        
        if in_quotes:
            if c == "\\" and i + 1 < len(line):
                current += c + line[i + 1]
                i += 2
                continue
            elif c == quote_char:
                current += c
                tokens.append(current)
                current = ""
                in_quotes = False
            else:
                current += c
        else:
            if c in ('"', "'"):
                if current:
                    tokens.append(current)
                    current = ""
                current = c
                in_quotes = True
                quote_char = c
            elif c.isspace():
                if current:
                    tokens.append(current)
                    current = ""
            else:
                current += c
        i += 1
    
    if current:
        tokens.append(current)
    
    return tokens


def parse_script(path: Path) -> Plan:
    """Parse a .demorec script file into an execution plan."""
    plan = Plan()
    current_segment: Segment | None = None
    pending_narration: Narration | None = None
    
    with open(path) as f:
        lines = f.readlines()
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Handle narration comments: # @narrate:before "text"
        if line.startswith("#"):
            narrate_match = re.match(r"#\s*@narrate:(before|during|after)\s+(.+)", line)
            if narrate_match:
                mode = narrate_match.group(1)
                text = parse_string(narrate_match.group(2).strip())
                pending_narration = Narration(mode=mode, text=text, line_num=line_num)
                continue
            
            # Handle voice directive: # @voice eleven:rachel
            voice_match = re.match(r"#\s*@voice\s+(\S+)", line)
            if voice_match:
                plan.voice = voice_match.group(1)
                continue
            
            # Regular comment - skip
            continue
        
        # Tokenize the line
        tokens = tokenize_line(line)
        if not tokens:
            continue
        
        cmd_name = tokens[0]
        cmd_args = [parse_string(t) for t in tokens[1:]]
        
        # Handle global directives
        if cmd_name == "Output":
            if cmd_args:
                plan.output = Path(cmd_args[0])
            continue
        
        if cmd_name == "Set":
            if len(cmd_args) >= 2:
                key = cmd_args[0].lower()
                val = cmd_args[1]
                if key == "width":
                    plan.width = int(val)
                elif key == "height":
                    plan.height = int(val)
                elif key == "framerate":
                    plan.framerate = int(val)
                elif key == "theme" and current_segment:
                    # Theme is segment-specific for terminal
                    current_segment.commands.append(Command("SetTheme", [val], line_num))
            continue
        
        # Handle mode switch
        if cmd_name == "@mode":
            if cmd_args:
                mode = cmd_args[0].lower()
                if mode in ("terminal", "browser"):
                    current_segment = Segment(mode=mode)
                    plan.segments.append(current_segment)
            continue
        
        # All other commands require an active segment
        if current_segment is None:
            # Default to terminal mode
            current_segment = Segment(mode="terminal")
            plan.segments.append(current_segment)
        
        # Create the command
        cmd = Command(name=cmd_name, args=cmd_args, line_num=line_num)
        cmd_index = len(current_segment.commands)
        current_segment.commands.append(cmd)
        
        # Attach pending narration to this command
        if pending_narration:
            current_segment.narrations[cmd_index] = pending_narration
            pending_narration = None
    
    return plan
