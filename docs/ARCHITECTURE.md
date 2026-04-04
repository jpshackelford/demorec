# demorec Architecture

This document describes the internal architecture of demorec, a tool for recording terminal and browser demos from a single script with narration support.

## Table of Contents

1. [Dependencies and Third-Party Tools](#dependencies-and-third-party-tools)
2. [System Overview](#system-overview)
3. [Recording Pipeline](#recording-pipeline)
4. [Terminal Recording Architecture](#terminal-recording-architecture)
5. [Terminal Size and Viewport Management](#terminal-size-and-viewport-management)
6. [Persistent Terminal Sessions](#persistent-terminal-sessions)
7. [Preview and Verification System](#preview-and-verification-system)
8. [Browser Recording](#browser-recording)
9. [Narration and Audio Pipeline](#narration-and-audio-pipeline)
10. [Component Relationships](#component-relationships)

---

## Dependencies and Third-Party Tools

demorec integrates several external tools and libraries. Understanding these dependencies is essential for development and troubleshooting.

### System Tools (External Binaries)

| Tool | Version | Purpose | Used By |
|------|---------|---------|---------|
| **[ttyd](https://github.com/tsl0922/ttyd)** | 1.7.7+ | WebSocket-based terminal server that bridges xterm.js to a real PTY | `ttyd.py` |
| **[tmux](https://github.com/tmux/tmux)** | 3.0+ | Terminal multiplexer for persistent sessions across mode switches | `ttyd.py` |
| **[FFmpeg](https://ffmpeg.org/)** | 4.0+ | Video concatenation, format conversion, audio mixing | `audio.py`, `modes/terminal.py` |
| **[vim](https://www.vim.org/)** | 8.0+ | Text editor (optional, only for vim primitives) | `modes/vim.py` |
| **[Marp CLI](https://github.com/marp-team/marp-cli)** | 3.0+ | Markdown presentation renderer (optional, only for presentation mode) | `marp.py` |

### Python Libraries

| Library | Purpose | Used By |
|---------|---------|---------|
| **[Playwright](https://playwright.dev/python/)** | Browser automation for both terminal (via xterm.js) and web recording | `modes/terminal.py`, `modes/browser.py`, `preview.py` |
| **[Click](https://click.palletsprojects.com/)** | CLI framework for command-line interface | `cli.py` |
| **[Rich](https://rich.readthedocs.io/)** | Terminal formatting, progress bars, and console output | `runner.py`, `cli.py` |
| **[edge-tts](https://github.com/rany2/edge-tts)** | Microsoft Edge text-to-speech (free, no API key) | `tts.py` |
| **[ElevenLabs](https://elevenlabs.io/)** | Premium TTS voices (optional, requires API key) | `tts.py` |

### JavaScript Libraries (Loaded via ttyd)

| Library | Purpose | Notes |
|---------|---------|-------|
| **[xterm.js](https://xtermjs.org/)** | Terminal emulator in the browser | Bundled with ttyd, renders ANSI output |
| **[xterm-addon-fit](https://github.com/xtermjs/xterm.js/tree/master/addons/addon-fit)** | Auto-fit terminal to container | Used for row count targeting |

### How Tools Interact

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          demorec (Python)                                │
├─────────────────────────────────────────────────────────────────────────┤
│  CLI (Click)  →  Parser  →  Runner  →  Recorders  →  Audio (FFmpeg)    │
└───────┬─────────────────────────────────────────────────────────────────┘
        │
        │ spawns processes / controls browser
        ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│      ttyd         │  │    Playwright     │  │      FFmpeg       │
│  (terminal PTY)   │  │ (browser control) │  │ (video/audio)     │
├───────────────────┤  ├───────────────────┤  ├───────────────────┤
│ • WebSocket server│  │ • Chromium browser│  │ • concat segments │
│ • PTY management  │  │ • Video recording │  │ • mix audio       │
│ • RESIZE protocol │  │ • Screenshot      │  │ • format convert  │
└─────────┬─────────┘  └─────────┬─────────┘  └───────────────────┘
          │                      │
          │ attaches to          │ renders
          ▼                      ▼
┌───────────────────┐  ┌───────────────────┐
│      tmux         │  │     xterm.js      │
│ (session persist) │  │ (terminal render) │
├───────────────────┤  ├───────────────────┤
│ • Named sessions  │  │ • ANSI rendering  │
│ • State preserve  │  │ • Font scaling    │
│ • Process isolate │  │ • fit() addon     │
└───────────────────┘  └───────────────────┘
```

### Version Compatibility Notes

- **Python**: Requires 3.10+ (uses `match` statements, type unions with `|`)
- **Playwright**: Uses async API; requires `playwright install chromium` after pip install
- **ttyd**: Must support `--writable` flag and WebSocket RESIZE_TERMINAL protocol
- **tmux**: Any recent version; status bar is disabled for clean recordings
- **FFmpeg**: Needs `libx264` encoder and `aac` audio codec support

---

## System Overview

demorec unifies terminal and browser recording into a single pipeline. The key insight is that **both modes use Playwright for rendering**—terminal segments render via xterm.js in a headless browser, enabling seamless video concatenation.

```
┌─────────────────────────────────────────────────────────────┐
│                     my-demo.demorec                         │
└────────────────────────┬────────────────────────────────────┘
                         │ parse (parser.py)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Segment Plan                             │
│   [terminal:0-15s] → [browser:15-45s] → [terminal:45-55s]   │
└────────────────────────┬────────────────────────────────────┘
                         │ Runner orchestrates
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌───────────┐   ┌───────────┐   ┌───────────┐
   │ Terminal  │   │  Browser  │   │ Terminal  │
   │  Recorder │   │  Recorder │   │  Recorder │
   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
         │               │               │
   ┌─────┴─────┐         │         ┌─────┴─────┐
   │  ttyd +   │         │         │  ttyd +   │
   │ xterm.js  │         │         │ xterm.js  │
   └─────┬─────┘         │         └─────┬─────┘
         │               │               │
    Playwright       Playwright     Playwright
    (video rec)      (video rec)    (video rec)
         │               │               │
         ▼               ▼               ▼
    segment_0.mp4   segment_1.mp4   segment_2.mp4
         │               │               │
         └───────────────┼───────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  FFmpeg Concat +    │
              │  TTS Audio Mix      │
              └──────────┬──────────┘
                         │
                         ▼
                    demo.mp4 (final)
```

---

## Recording Pipeline

### Parser (`parser.py`)

The parser transforms `.demorec` scripts into an execution `Plan`:

```python
@dataclass
class Plan:
    output: Path              # Output file (e.g., demo.mp4)
    width: int = 1280         # Video width
    height: int = 720         # Video height  
    framerate: int = 30
    voice: str | None         # TTS voice (e.g., edge:jenny)
    segments: list[Segment]   # List of recording segments
```

Each `Segment` represents a continuous block in a single mode:

```python
@dataclass
class Segment:
    mode: Literal["terminal", "browser", "presentation"]
    submode: str | None = None       # e.g., "vim" for terminal:vim
    session_name: str = "default"    # Session name via 'name' setting
    commands: list[Command]
    narrations: dict[int, Narration]  # cmd_index → narration
    size: str | None                  # Terminal size preset
    rows: int | None                  # Explicit row count
```

Session names are specified via the `name` setting after `@mode`, not via colon syntax (which is reserved for sub-modes like `terminal:vim`).

The parser uses a `_Tokenizer` class to handle quoted strings with escape sequences, and `_ParseContext` to track state during parsing. Settings mode is entered after `@mode` and ends on a blank line or `---` delimiter.

### Runner (`runner.py`)

The `Runner` orchestrates the recording pipeline:

1. **Preflight phase**: Checks dependencies (vim, marp CLI, etc.)
2. **Narration phase**: Pre-generates all TTS audio clips
3. **Recording phase**: Records each segment, tracking command timestamps
4. **Concat phase**: Joins segments with FFmpeg
5. **Subtitle phase**: Generates SRT file from narration timing
6. **Audio phase**: Mixes narration audio at correct timestamps

```python
class Runner:
    def __init__(self, plan: Plan):
        self._session_manager = TerminalSessionManager()
        # Sessions persist across segments
    
    def _record_segment(self, segment: Segment, output: Path, time_offset: float):
        recorder = self._create_recorder(segment)  # Terminal or Browser
        timestamps = recorder.record(segment, output, timed_narrations)
        self._update_narration_times(timed_narrations, timestamps, time_offset)
```

---

## Terminal Recording Architecture

Terminal recording is the most complex subsystem, involving multiple layers of coordination between the ANSI terminal, web viewport, and underlying PTY.

### The ttyd + xterm.js Stack

```
┌─────────────────────────────────────────────────────┐
│                  Playwright Browser                  │
│  ┌───────────────────────────────────────────────┐  │
│  │              xterm.js Terminal                │  │
│  │  ┌─────────────────────────────────────────┐  │  │
│  │  │        Visible Viewport (720p)          │  │  │
│  │  │  ┌───────────────────────────────────┐  │  │  │
│  │  │  │   ANSI-rendered terminal output   │  │  │  │
│  │  │  │   with colors, styles, cursor     │  │  │  │
│  │  │  └───────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────┘  │
│              │ WebSocket connection                  │
└──────────────┼──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│                    ttyd Server                       │
│  ┌───────────────────────────────────────────────┐  │
│  │  WebSocket ←→ PTY bridge with RESIZE support   │  │
│  └───────────────────────────────────────────────┘  │
│              │ ioctl(TIOCSWINSZ)                     │
└──────────────┼──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│                  PTY (bash/tmux)                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  Real shell with ANSI support, vim, etc.      │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Why ttyd?

xterm.js is just a renderer—it needs something to connect to. ttyd provides:

1. **Real PTY**: Actual shell execution with job control, signals, etc.
2. **WebSocket bridge**: Connects xterm.js to the PTY
3. **RESIZE_TERMINAL protocol**: Propagates terminal size changes to the PTY via `ioctl(TIOCSWINSZ)`
4. **tmux integration**: Enables persistent sessions

### TerminalRecorder (`modes/terminal.py`)

```python
class TerminalRecorder(CommandExecutorMixin):
    SIZE_PRESETS = {
        "large": 24,   # Classic terminal, easy to read
        "medium": 36,  # Balanced readability and content
        "small": 44,   # Default xterm.js density
        "tiny": 50,    # Maximum content, smaller text
    }
    
    async def _record_async(self, segment, output):
        # 1. Get or create terminal session
        port, owns_session = await self._setup_session()
        
        # 2. Run browser session with Playwright
        timestamps, setup_dur = await self._run_browser_session(segment, output, port)
        
        # 3. Finalize video (trim setup, convert to mp4)
        self._finalize_video(output, trim_start=setup_dur)
```

---

## Terminal Size and Viewport Management

One of the most complex challenges is ensuring the ANSI terminal, xterm.js, and web viewport are all synchronized. When a user requests 30 rows, the system must:

1. Calculate the correct font size for 30 rows in 720p
2. Configure xterm.js with that font size
3. Sync the PTY to also have 30 rows

### The Row Synchronization Problem

```
User specifies: rows 30    (or legacy: @terminal:rows 30)

What needs to happen:
  ┌─────────────────────────────────────────┐
  │  720p viewport (1280×720 pixels)        │
  │                                          │
  │  xterm.js calculates:                   │
  │    font_size = f(viewport, rows)        │
  │    → fontSize ≈ 20px for 30 rows        │
  │                                          │
  │  term.fit() fires onResize event        │
  │    → ttyd WebSocket sends RESIZE_TERMINAL│
  │    → PTY receives ioctl(TIOCSWINSZ)     │
  │    → PTY now also has 30 rows           │
  │                                          │
  │  Result: vim, less, etc. all see 30 rows │
  └─────────────────────────────────────────┘
```

### The Playwright device_scale_factor Gotcha

**Critical**: Always use `device_scale_factor=1` with Playwright:

```python
context = await browser.new_context(
    viewport={"width": 1280, "height": 720},
    device_scale_factor=1,  # NOT 2!
    record_video_dir=str(output.parent),
)
```

A scale factor of 2 causes xterm.js to render at 2× resolution, making characters appear half-sized and doubling the apparent row count. This was a major source of terminal size mismatch bugs.

### xterm.js Configuration (`xterm.py`)

The xterm module provides async functions to configure terminals:

```python
@dataclass
class TerminalConfig:
    font_size: int = 14
    font_family: str = "Monaco, 'Cascadia Code', 'Fira Code', monospace"
    line_height: float = 1.0
    theme: dict | None = None
    desired_rows: int | None = None
```

### Row Fitting Algorithm (`js/setup_terminal.js`)

The JavaScript runs in the browser to configure xterm.js:

```javascript
// 1. Make container fill viewport
container.style.width = '100vw';
container.style.height = '100vh';

// 2. Fit with default font to get baseline rows
term.fit();
const baselineRows = term.rows;  // e.g., 44 rows at 14px

// 3. Scale font to achieve desired rows
if (config.desiredRows && config.desiredRows !== baselineRows) {
    // If we want 30 rows but got 44, scale font up
    finalFontSize = Math.round(14 * (44 / 30));  // ≈ 20px
    term.options.fontSize = finalFontSize;
    term.fit();  // Re-fit with new font size
}
```

### Iterative Refinement (`js/fit_to_rows.js`)

Sometimes one adjustment isn't enough. The `fit_to_rows` function iteratively refines:

```javascript
(desiredRows) => {
    const currentRows = term.rows;
    if (currentRows === desiredRows) return { done: true, ... };
    
    // Proportional adjustment
    const newFontSize = Math.round(currentFontSize * (currentRows / desiredRows));
    term.options.fontSize = newFontSize;
    term.fit();  // This triggers PTY resize via ttyd
    
    return { rows: term.rows, done: term.rows === desiredRows };
}
```

### The term.fit() Magic

When `term.fit()` is called:

1. xterm.js calculates rows/cols based on viewport and font
2. Fires an `onResize` event
3. ttyd's JavaScript catches this and sends `RESIZE_TERMINAL` via WebSocket
4. ttyd server receives the message and calls `ioctl(TIOCSWINSZ)` on the PTY
5. The shell/vim/etc. receive SIGWINCH and update their row counts

This is why `term.fit()` is the key—it handles both the visual and PTY sides in one call.

---

## Persistent Terminal Sessions

### The Problem

Real demos often need to:
- Start a server in one terminal
- Switch to browser to see the UI
- Switch to another terminal to run client commands
- Return to the server terminal to see logs

Without persistence, each `@mode terminal` would start a fresh shell.

### The Solution: tmux + Named Sessions

```python
class TerminalSession:
    """Manages a single persistent terminal session via ttyd + tmux."""
    
    def start(self):
        ensure_tmux_session(self.name)  # Creates demorec-{name}
        self._process = start_ttyd(port, session_name=self.name)
```

When ttyd is started with a session name, it runs:
```bash
tmux attach-session -t demorec-{session_name}
```

This means:
- The tmux session persists when ttyd disconnects
- Reconnecting ttyd attaches to the same session
- All state (cwd, env vars, running processes) is preserved

### TerminalSessionManager

```python
class TerminalSessionManager:
    """Manages multiple named terminal sessions."""
    
    def get_or_create(self, name: str = "default") -> TerminalSession:
        if name not in self._sessions:
            session = TerminalSession(name)
            session.start()
            self._sessions[name] = session
        return self._sessions[name]
```

### Session Flow Example

```tape
@mode terminal
name "server"               # Creates demorec-server tmux session
---
Type "python -m http.server"
Enter

@mode browser               # Server keeps running!
Navigate "http://localhost:8000"

@mode terminal
name "client"               # Creates demorec-client (independent)
---
Type "curl localhost:8000"
Enter

@mode terminal
name "server"               # Reconnects to server session
---
# Shows server logs from the requests
```

### Clean Environment for tmux Sessions

Sessions are created with a clean shell environment:

```python
def _create_tmux_session(tmux_session: str):
    cmd = [
        "tmux", "new-session", "-d", "-s", tmux_session,
        "/usr/bin/env", "PS1=$ ", "/bin/bash", "--norc", "--noprofile",
    ]
    subprocess.run(cmd, env=make_clean_env())
    # Also disable tmux status bar
    subprocess.run(["tmux", "set-option", "-t", tmux_session, "status", "off"])
```

This avoids PS1JSON artifacts from OpenHands environments and ensures consistent prompt display.

---

## Preview and Verification System

The preview system runs scripts without recording video, focusing on verification and debugging.

### TerminalPreviewer (`preview.py`)

For terminal-only scripts with checkpoint verification:

```python
class TerminalPreviewer:
    async def _run_commands(self, page, segment, checkpoints, screenshot_dir):
        for cmd_idx, cmd in enumerate(segment.commands):
            await self._execute_command(page, cmd)
            
            # Capture frame if enabled
            if self._state.capture_frames:
                await capture_frame(self._state, page, "terminal")
            
            # Verify checkpoint if this command triggers one
            if cmd_idx in checkpoint_map:
                result = await self._verify_checkpoint(page, cp, ...)
                results.append(result)
```

### Checkpoint Detection

Checkpoints are auto-detected from vim visual selection patterns:

```python
def _detect_checkpoints_from_commands(self, commands):
    # Look for patterns like:
    #   Type "27G"    # Goto line 27
    #   Type "V"      # Start visual mode
    #   Type "35G"    # Extend to line 35
    #   Escape        # <-- Checkpoint here!
```

### Checkpoint Verification

At each checkpoint, the system:
1. Gets the terminal buffer state via `get_buffer_state.js`
2. Parses vim line numbers from visible lines
3. Checks if expected lines are within the visible viewport

```python
def _check_visibility(self, expected, visible):
    expected_start, expected_end = expected
    visible_start, visible_end = visible
    
    if expected_start < visible_start:
        return False, f"Line {expected_start} not visible"
    if expected_end > visible_end:
        return False, f"Line {expected_end} not visible"
    return True, None
```

### Frame-by-Frame Capture

For AI debugging, the preview system can capture every terminal state:

```bash
demorec preview script.demorec --rows 30 -o ./frames
```

Output:
```
frames/
├── frame_0001_0000.00.txt    # Initial state
├── frame_0002_0000.05.txt    # After first command
├── frame_0003_0000.28.txt    # After Type "vim file.py"
└── frame_0004_0001.52.txt    # After Enter
```

Frame naming: `frame_{NNNN}_{SSSS.ss}.{ext}`
- `NNNN`: Zero-padded 4-digit frame number
- `SSSS.ss`: Elapsed time in seconds
- `ext`: `.txt` for terminal, `.png` for browser

### Buffer State Extraction (`js/get_buffer_state.js`)

```javascript
() => {
    const term = window.term;
    const buffer = term.buffer.active;
    const visibleLines = [];
    
    for (let i = 0; i < term.rows; i++) {
        const line = buffer.getLine(buffer.viewportY + i);
        visibleLines.push(line?.translateToString() || '');
    }
    
    return {
        rows: term.rows,
        cols: term.cols,
        viewportY: buffer.viewportY,
        visibleLines
    };
}
```

### ScriptPreviewer

For scripts with multiple segments (terminal + browser), `ScriptPreviewer` maintains continuous frame numbering:

```python
class ScriptPreviewer:
    async def _preview_async(self, script_path, segments, output_dir):
        init_start_time(self._state)  # Single timer for all segments
        
        for segment in segments:
            if segment.mode == "terminal":
                await self._preview_terminal_segment(segment, ...)
            else:
                await self._preview_browser_segment(segment, ...)
```

---

## Browser Recording

Browser recording uses Playwright directly without ttyd.

### BrowserRecorder (`modes/browser.py`)

```python
class BrowserRecorder(CommandExecutorMixin):
    async def _record_async(self, segment, output):
        async with async_playwright() as p:
            context, page = await self._create_browser_context(p, output)
            timestamps = await self._execute_commands(page, segment)
            await context.close()
        
        self._finalize_video(output)
        return timestamps
```

### Browser Commands

```python
BROWSER_COMMANDS = {
    "Navigate": _cmd_navigate,  # page.goto()
    "Click": _cmd_click,        # page.click()
    "Type": _cmd_type,          # page.type() with delay
    "Fill": _cmd_fill,          # page.fill() instant
    "Press": _cmd_press,        # page.keyboard.press()
    "Sleep": _cmd_sleep,        # asyncio.sleep()
    "Wait": _cmd_wait,          # page.wait_for_selector()
    "Scroll": _cmd_scroll,      # window.scrollBy()
    "Hover": _cmd_hover,        # page.hover()
    "Highlight": _cmd_highlight, # CSS outline injection
    "Unhighlight": _cmd_unhighlight,
    "Screenshot": _cmd_screenshot,
}
```

---

## Narration and Audio Pipeline

### TTS Engines (`tts.py`)

Two TTS backends are supported:

1. **Edge TTS** (free, high quality):
   ```python
   # edge:jenny, edge:guy, edge:aria, etc.
   communicate = edge_tts.Communicate(text, voice)
   await communicate.save(output_path)
   ```

2. **ElevenLabs** (paid, highest quality):
   ```python
   # eleven:rachel, eleven:adam, etc.
   client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
   audio = client.generate(text=text, voice=voice_name)
   ```

### Narration Timing

Narrations are attached to commands with timing modes:

```tape
# @narrate:before "Let's install the CLI tool."
Type "pip install myapp"

# @narrate:during "This takes a few seconds."
Enter

# @narrate:after "Installation complete!"
Sleep 2s
```

The Runner pre-generates all audio, then adjusts start times based on recorded command timestamps:

```python
def _update_narration_times(self, timed_narrations, timestamps, offset):
    for cmd_idx, timed in timed_narrations.items():
        cmd_start, cmd_end = timestamps[cmd_idx]
        
        if timed.mode == "before":
            timed.start_time = offset + cmd_start - timed.duration
        elif timed.mode == "during":
            timed.start_time = offset + cmd_start
        elif timed.mode == "after":
            timed.start_time = offset + cmd_end
```

### FFmpeg Audio Mixing (`audio.py`)

Non-overlapping narration clips are mixed with `adelay` filters:

```python
def _build_audio_filter(narrations):
    # For each narration, create adelay filter
    for i, n in enumerate(narrations):
        delay_ms = int(max(0, n.start_time) * 1000)
        filter_parts.append(f"[{i + 1}:a]adelay={delay_ms}|{delay_ms}[a{i}]")
    
    # Mix all delayed tracks
    amix_filter = f"{mix_inputs}amix=inputs={len(narrations)}:normalize=0:dropout_transition=0[aout]"
```

The `normalize=0` and `dropout_transition=0` options prevent volume fluctuations as clips start/end.

### SRT Subtitle Generation

```python
def generate_srt(narrations, output_path):
    for i, n in enumerate(narrations, 1):
        start = max(0, n.start_time)
        end = start + n.duration
        lines = split_caption(n.text, max_len=42)  # Word-wrap long captions
        
        f.write(f"{i}\n")
        f.write(f"{format_srt_time(start)} --> {format_srt_time(end)}\n")
        f.write(f"{'\n'.join(lines)}\n\n")
```

---

## Component Relationships

### Module Dependencies

```
cli.py
  ├── parser.py          # Parse .demorec files
  ├── runner.py          # Orchestrate recording
  │     ├── modes/terminal.py
  │     │     ├── ttyd.py       # ttyd process management
  │     │     ├── xterm.py      # xterm.js configuration
  │     │     ├── vim.py        # Vim command expansion
  │     │     └── terminal_commands.py  # Themes, handlers
  │     ├── modes/browser.py
  │     └── audio.py           # FFmpeg operations
  ├── preview.py         # Preview/verification
  │     ├── frame_capture.py   # Frame capture utilities
  │     └── xterm.py           # Buffer state extraction
  └── stage.py           # Vim stage direction calculator
```

### JavaScript Assets (`js/`)

```
js/
├── setup_terminal.js     # Full viewport + row targeting
├── fit_to_rows.js        # Iterative font adjustment
├── get_buffer_state.js   # Buffer inspection for preview
└── setup_container.js    # Simple container setup
```

### Data Flow Summary

```
.demorec file
    │
    ▼ parse_script()
Plan with Segments
    │
    ▼ Runner.run()
    │
    ├─► Pre-generate TTS audio
    │
    ├─► For each segment:
    │     ├─► TerminalRecorder or BrowserRecorder
    │     ├─► Playwright records video
    │     └─► Track command timestamps
    │
    ├─► FFmpeg concat segments
    │
    ├─► Generate SRT subtitles
    │
    └─► FFmpeg mix audio at timestamps
           │
           ▼
       Final video with narration
```

---

## Key Learnings

1. **Unified Rendering**: Using Playwright for both terminal (via xterm.js) and browser enables seamless video concatenation with consistent dimensions.

2. **ttyd for Real PTY**: xterm.js alone is just a renderer. ttyd provides actual shell execution with full ANSI support.

3. **term.fit() Is Magic**: It handles both xterm.js resizing AND PTY synchronization via ttyd's WebSocket protocol.

4. **device_scale_factor=1**: Critical for correct terminal sizing. Scale factor 2 doubles apparent rows.

5. **tmux for Persistence**: Named sessions preserve state across mode switches, enabling server/client demos.

6. **Pre-generate Audio**: Generate all TTS clips before recording, then adjust timing based on actual command timestamps.

7. **amix normalize=0**: Prevents volume fluctuations when mixing sequential narration clips.
