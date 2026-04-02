# demorec 🎬

**Record CLI and web-based demos from a single script.**

demorec is a declarative tool for creating professional demo videos that seamlessly mix terminal and browser interactions—perfect for product demos, tutorials, and PR walkthroughs.

Inspired by [charmbracelet/vhs](https://github.com/charmbracelet/vhs), but unified across CLI and web.

## Why demorec?

Real-world demos often involve both terminal and browser:

- Start a server via CLI → show the web UI
- Run a build command → verify results in browser  
- Configure via terminal → interact with the app

Existing tools make you record these separately and stitch manually. **demorec handles it all in one script.**

### Key Features

- **Unified Recording**: Seamlessly switch between terminal and browser in a single script
- **Multiple Terminal Sessions**: Run servers, clients, and utilities in independent terminals (`@mode terminal:server`, `@mode terminal:client`)
- **Persistent State**: Terminal state (working directory, environment variables, running processes) persists across mode switches
- **AI Narration**: Add voiceover with Edge TTS (free) or ElevenLabs
- **Vim Primitives**: High-level commands for code review demos (`Open`, `Highlight`, `Goto`, `Close`)

## Quick Example

```tape
# my-demo.demorec
Output demo.mp4
Set Width 1280
Set Height 720

# @voice edge:jenny

# ─────────────────────────────────────
# TERMINAL: Install and start server
# ─────────────────────────────────────
@mode terminal
Set Theme "Dracula"

# @narrate:before "Let's install the CLI tool."
Type "pip install myapp"
Enter
Sleep 2s

# @narrate:before "Now let's start the dev server."
Type "myapp serve --port 3000"
Enter
Sleep 3s

# ─────────────────────────────────────
# BROWSER: Show the web interface
# ─────────────────────────────────────
@mode browser

# @narrate:before "The web interface is now live."
Navigate "http://localhost:3000"
Sleep 2s

Click "#create-new"
Type "#name" "My Project"
Click "#save"
Sleep 2s

# ─────────────────────────────────────
# TERMINAL: Show the logs
# ─────────────────────────────────────
@mode terminal

# @narrate:after "And we can see the request in the terminal logs."
Sleep 2s
Ctrl+C
Sleep 1s
```

```bash
demorec record my-demo.demorec
```

## Installation

```bash
# With uv (recommended)
uv tool install demorec

# Or with pip
pip install demorec

# Install browser dependencies
demorec install
```

## CLI Usage

```bash
# Record a demo
demorec record my-demo.demorec

# Record with options
demorec record my-demo.demorec -o output.mp4 --voice adam

# Validate syntax without recording
demorec validate my-demo.demorec

# List available TTS voices
demorec voices

# Show version
demorec --version
```

## Agent Workflow Tools

demorec includes commands designed for AI agents creating vim-based code review demos.

### Stage Directions

Calculate optimal vim commands to display specific line ranges:

```bash
# Get vim commands for highlighting specific line ranges
demorec stage --rows 30 --highlights "6-8,11-16,27-35,63-73"

# Output formats: text (default), json, demorec
demorec stage --rows 30 --highlights "6-8,27-35" --format json
demorec stage --rows 30 --highlights "6-8,27-35" --format demorec
```

Example output:
```
Stage Directions (30 rows)

Block 1: lines 6-8 (3 lines)
  Goto:      6G
  Center:    zz
  Select:    V8G
  Rationale: Block fits in viewport, using zz to center

Block 2: lines 27-35 (9 lines)  
  Goto:      31G
  Center:    zz
  Select:    V27G then 35G
  Rationale: Block fits in viewport, centering on middle line
```

### Preview

Run through a script and verify checkpoints without recording video:

```bash
# Preview with verification (screenshots only on errors)
demorec preview script.demorec --rows 30

# Always capture screenshots at checkpoints
demorec preview script.demorec --rows 30 --screenshots

# Never capture screenshots (fastest)
demorec preview script.demorec --rows 30 --no-screenshots

# Capture frame-by-frame snapshots for AI debugging
demorec preview script.demorec --rows 30 -o ./frames

# Capture frames without output directory (disable frame capture explicitly)
demorec preview script.demorec --rows 30 -o ./frames --no-frames
```

Preview auto-detects "show moments" (visual selections in vim) and verifies that expected lines are visible:

```
[PASS] Checkpoint 1 (line 11): lines 6-8 visible
[PASS] Checkpoint 2 (line 33): lines 27-35 visible
Frames captured: 15 frames to ./frames
Summary: 2/2 passed
```

#### Frame-by-Frame Capture

When `--output-dir` is specified (or `--frames` is used), preview captures the terminal/browser state at every step:

- **Terminal frames**: Saved as `.txt` files containing the visible terminal buffer
- **Browser frames**: Saved as `.png` screenshots

Frame naming convention: `frame_{NNNN}_{SSSS.ss}.{ext}`
- `NNNN`: Zero-padded 4-digit frame number (0001, 0002, ...)
- `SSSS.ss`: Elapsed time in seconds with 2 decimal places (0000.00, 0001.25, ...)
- `ext`: File extension (`.txt` for terminal, `.png` for browser)

Example output:
```
frames/
├── frame_0001_0000.00.txt    # Initial terminal state
├── frame_0002_0000.05.txt    # After first command
├── frame_0003_0000.28.txt    # After Type "vim file.py"
├── frame_0004_0001.52.txt    # After Enter
└── ...
```

This is useful for AI agents debugging recordings and verifying terminal output at each step.

### Checkpoints

Analyze a script to find natural checkpoint locations:

```bash
# List detected checkpoints
demorec checkpoints script.demorec

# JSON output for programmatic use
demorec checkpoints script.demorec --format json
```

### Terminal Sizing

Control terminal dimensions for consistent viewport sizing:

```tape
@terminal:rows 30           # Exact row count (10-100)
@terminal:size medium       # Use a preset size

@mode terminal
Set Theme "Dracula"
Type "vim myfile.py"
Enter
```

**Size presets:**

| Preset | Rows | Best for |
|--------|------|----------|
| `large` | 24 | Classic terminal, easy to read |
| `medium` | 36 | Balanced readability and content |
| `small` | 44 | Default xterm.js density |
| `tiny` | 50 | Maximum content, smaller text |

### High-Level Vim Primitives

For AI agents creating code review demos, these commands handle vim complexity internally:

```tape
@mode terminal
@terminal:rows 30

Open "src/api.py"           # Open file with line numbers enabled
Highlight "10-20"           # Navigate to lines and select visually
Highlight "45-55"           # Jump to next highlight
Goto 100                    # Jump to line with centering
Close                       # Exit vim cleanly
```

| Command | Description | Example |
|---------|-------------|---------|
| `Open "<file>"` | Open file in vim with line numbers | `Open "src/api.py"` |
| `Highlight "<range>"` | Navigate to lines and select visually | `Highlight "10-20"` |
| `Goto <line>` | Jump to specific line with centering | `Goto 50` |
| `Close` | Exit vim cleanly | `Close` |

### Complete Agent Workflow

```bash
# 1. View file with line numbers
cat -n examples/sample_code.py

# 2. Get stage directions for highlights
demorec stage --rows 30 --highlights "6-8,11-16,27-35"

# 3. Write the .demorec script using generated vim commands

# 4. Preview to verify checkpoints
demorec preview script.demorec --rows 30

# 5. If issues, adjust script and re-preview

# 6. Record final video
demorec record script.demorec
```

## DSL Reference

### Global Settings

```tape
Output demo.mp4              # Output file (.mp4, .webm)
Set Width 1280               # Video width
Set Height 720               # Video height  
Set Framerate 30             # Video framerate
```

### Mode Switching & Multiple Terminal Sessions

demorec supports switching between terminal and browser modes, with **persistent terminal sessions** that maintain state across mode switches.

```tape
@mode terminal               # Default terminal session
@mode terminal:server        # Named session "server" (independent)
@mode terminal:client        # Named session "client" (independent)
@mode browser                # Browser recording
```

#### Session Persistence

Each terminal session is backed by tmux, which means:

| What Persists | Example |
|---------------|---------|
| Working directory | `cd /app` stays in `/app` after switching modes |
| Environment variables | `export API_KEY=xxx` remains set |
| Running processes | `python server.py &` keeps running |
| Command history | Up arrow recalls previous commands |

#### Named Sessions vs Default Session

| Session | Syntax | Use Case |
|---------|--------|----------|
| Default | `@mode terminal` | General commands, setup |
| Named | `@mode terminal:server` | Long-running server process |
| Named | `@mode terminal:client` | Client/testing commands |
| Named | `@mode terminal:logs` | Tail logs or monitoring |

Named sessions are **completely independent**—each has its own shell process, environment, and working directory. The default session (`@mode terminal`) is also persistent but separate from named sessions.

#### Typical Multi-Session Workflow

```tape
# 1. Start server in dedicated session
@mode terminal:server
Type "npm run dev"
Enter
Sleep 2s

# 2. Switch to browser - server keeps running!
@mode browser
Navigate "http://localhost:3000"
Sleep 2s

# 3. Make API calls from client session
@mode terminal:client  
Type "curl localhost:3000/api/health"
Enter

# 4. Return to server session - see the request logs
@mode terminal:server
Sleep 1s
```

#### Tips for Effective Use

1. **Set up state early:** Initialize environment variables and working directories at the start—they persist throughout.

2. **Use named sessions for servers:** Start long-running processes in `terminal:server` so switching modes won't kill them.

3. **Show state preservation explicitly:** Run `pwd` or `echo $VAR` after switching back to demonstrate persistence—viewers love this!

4. **Clean up gracefully:** Use `Ctrl+C` in server terminals before ending to show clean shutdown.

5. **Use meaningful names:** Prefer `terminal:api`, `terminal:frontend`, `terminal:logs` over generic names.

### Terminal Commands

| Command | Description | Example |
|---------|-------------|---------|
| `Set Theme "<name>"` | Terminal theme | `Set Theme "Dracula"` |
| `Type "<text>"` | Type text with delay | `Type "echo hello"` |
| `Enter` | Press Enter | `Enter` |
| `Run "<cmd>" [wait]` | Type, execute, and wait | `Run "npm test" 3s` |
| `Sleep <time>` | Pause | `Sleep 2s` or `Sleep 500ms` |
| `Ctrl+C` | Send interrupt | `Ctrl+C` |
| `Ctrl+D` | Send EOF | `Ctrl+D` |
| `Ctrl+L` | Clear screen | `Ctrl+L` |
| `Ctrl+Z` | Suspend process | `Ctrl+Z` |
| `Tab` | Press Tab (autocomplete) | `Tab` |
| `Up` / `Down` | Arrow keys (history) | `Up` |
| `Backspace [n]` | Delete characters | `Backspace 5` |
| `Escape` | Press Escape | `Escape` |
| `Space` | Press Space | `Space` |
| `Clear` | Clear terminal | `Clear` |
| `Hide` | Stop recording frames | `Hide` |
| `Show` | Resume recording | `Show` |

### Browser Commands

| Command | Description | Example |
|---------|-------------|---------|
| `Navigate "<url>"` | Go to URL | `Navigate "http://localhost:3000"` |
| `Click "<selector>"` | Click element | `Click "#submit-btn"` |
| `Type "<selector>" "<text>"` | Type into element | `Type "#email" "user@example.com"` |
| `Fill "<selector>" "<text>"` | Fill instantly | `Fill "#name" "John"` |
| `Press "<key>"` | Press key | `Press "Enter"` |
| `Sleep <time>` | Pause | `Sleep 2s` |
| `Wait "<selector>"` | Wait for element | `Wait ".loaded"` |
| `Scroll "<dir>" <amount>` | Scroll page | `Scroll "down" "300"` |
| `Hover "<selector>"` | Hover element | `Hover ".tooltip"` |
| `Highlight "<selector>"` | Add red outline | `Highlight "#important"` |
| `Unhighlight "<selector>"` | Remove outline | `Unhighlight "#important"` |
| `Screenshot "<file>"` | Save screenshot | `Screenshot "step1.png"` |

### Narration (AI Voice-Over)

```tape
# Set the voice
# @voice edge:jenny            # Microsoft Edge TTS (recommended, free)
# @voice eleven:rachel         # ElevenLabs (requires API key)

# Narration modes
# @narrate:before "Spoken before the next action"
# @narrate:during "Spoken while action runs"
# @narrate:after "Spoken after action completes"
```

**Microsoft Edge TTS voices (free, high quality - recommended):**

| Voice | Description |
|-------|-------------|
| `edge:jenny` | Female, US (default) |
| `edge:guy` | Male, US |
| `edge:aria` | Female, US |
| `edge:davis` | Male, US |
| `edge:emma` | Female, US |
| `edge:brian` | Male, US |
| `edge:sonia` | Female, UK |
| `edge:ryan` | Male, UK |
| `edge:natasha` | Female, AU |
| `edge:william` | Male, AU |

**ElevenLabs voices (requires paid API subscription):**

`eleven:rachel`, `eleven:adam`, `eleven:josh`, `eleven:bella`, `eleven:sam`, `eleven:antoni`, `eleven:arnold`, `eleven:domi`, `eleven:elli`

### Time Formats

- Seconds: `2s`, `1.5s`
- Milliseconds: `500ms`, `100ms`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ELEVENLABS_API_KEY` | ElevenLabs API key (only needed for ElevenLabs voices) |

Edge TTS works without any API key and is recommended for most use cases.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     my-demo.demorec                         │
└────────────────────────┬────────────────────────────────────┘
                         │ parse
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Segment Plan                             │
│   [terminal:0-15s] → [browser:15-45s] → [terminal:45-55s]   │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌───────────┐   ┌───────────┐   ┌───────────┐
   │ Terminal  │   │  Browser  │   │ Terminal  │
   │  (xterm)  │   │(Playwright)│  │  (xterm)  │
   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
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

**Key insight:** Both terminal and browser recording use Playwright. Terminal segments render via xterm.js in a headless browser, enabling seamless video concatenation.

For detailed architecture documentation including terminal size management, persistent sessions, preview verification, and more, see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Examples

### Bug Fix Demo

```tape
Output bugfix-demo.mp4
Set Width 1280
Set Height 720

# @voice edge:guy

@mode terminal
Set Theme "Dracula"

# @narrate:before "This demo shows the fix for issue 42."
Type "git checkout fix/issue-42"
Enter
Sleep 1s

Type "npm test"
Enter
Sleep 3s

# @narrate:after "All tests pass. The bug is fixed!"
Sleep 2s
```

### Full Stack Demo

```tape
Output fullstack-demo.mp4

# @voice edge:jenny

@mode terminal
Set Theme "GitHub Dark"

# @narrate:before "Let's start the backend server."
Type "cd backend && npm start"
Enter
Sleep 3s

@mode browser

# @narrate:before "Now let's see the frontend."
Navigate "http://localhost:3000"
Sleep 2s

# @narrate:during "I'll create a new user account."
Click "a.signup"
Type "#email" "demo@example.com"
Type "#password" "SecurePass123"
Click "#submit"
Sleep 3s

# @narrate:after "Account created successfully!"
Sleep 2s
```

### Multiple Terminal Sessions

This example demonstrates a server/client workflow with persistent state:

```tape
Output multi-terminal-demo.mp4
Set Width 1280
Set Height 720

# ─────────────────────────────────────
# Set up environment in default terminal
# ─────────────────────────────────────
@mode terminal
Type "export API_KEY='demo-key-123'"
Enter
Type "cd /tmp && mkdir -p myapp && cd myapp"
Enter
Sleep 500ms

# ─────────────────────────────────────
# Start server in named terminal
# ─────────────────────────────────────
@mode terminal:server
Type "cd /tmp/myapp"
Enter
Type "echo '<h1>Hello World</h1>' > index.html"
Enter
Type "python3 -m http.server 3000"
Enter
Sleep 2s

# ─────────────────────────────────────
# View in browser (server keeps running!)
# ─────────────────────────────────────
@mode browser
Navigate "http://localhost:3000"
Sleep 2s

# ─────────────────────────────────────
# Test from client terminal
# ─────────────────────────────────────
@mode terminal:client
Type "curl http://localhost:3000/"
Enter
Sleep 1s

# ─────────────────────────────────────
# Check server logs (session preserved)
# ─────────────────────────────────────
@mode terminal:server
# We see the server still running with request logs
Sleep 2s

# ─────────────────────────────────────
# Original terminal state is intact!
# ─────────────────────────────────────
@mode terminal
Type "echo $API_KEY && pwd"
Enter
# Shows: demo-key-123 and /tmp/myapp
Sleep 1s

# ─────────────────────────────────────
# Clean up
# ─────────────────────────────────────
@mode terminal:server
Ctrl+C
Sleep 500ms
```

**Key points demonstrated:**
- State in `terminal` (env vars, working dir) persists across all mode switches
- Server in `terminal:server` keeps running while you switch to browser and client
- Each named session is independent—`terminal:client` doesn't share state with `terminal:server`
- Returning to any terminal reconnects to the same session

### Code Review Demo (Vim Primitives)

```tape
Output code-review.mp4
Set Width 1280
Set Height 720

# @voice edge:jenny

@mode terminal
@terminal:rows 30
Set Theme "Dracula"

# Open the file using high-level primitives
Open "src/api.py"
Sleep 0.5s
# @narrate:after "Let's review this API client code."
Sleep 1s

# Highlight the imports
Highlight "4-7"
Sleep 0.5s
# @narrate:after "First, notice the imports for dataclasses and typing."
Sleep 1s

# Highlight the main class
Highlight "10-25"
Sleep 0.5s
# @narrate:after "Here's our User dataclass with type hints."
Sleep 1s

# Highlight error handling
Highlight "45-55"
Sleep 0.5s
# @narrate:after "The error handling follows best practices."
Sleep 1s

# Exit cleanly
Close
Sleep 0.5s
# @narrate:after "That's a quick tour of the code!"
Sleep 1s
```

---

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Project structure with `pyproject.toml` (uv-compatible)
- [ ] CLI entry point with `click`
- [ ] DSL parser for `.demorec` files
- [ ] Segment planner (split script by `@mode` switches)

### Phase 2: Terminal Recording
- [ ] xterm.js HTML template with Dracula theme
- [ ] Terminal runner using Playwright
- [ ] Support: `Type`, `Enter`, `Sleep`, `Ctrl+X`
- [ ] Theme support (Dracula, GitHub Dark, etc.)
- [ ] Fix terminal height to full line increments
- [ ] ANSI color and styling support (verified in POC)

### Phase 3: Browser Recording  
- [ ] Browser runner using Playwright
- [ ] Support: `Navigate`, `Click`, `Type`, `Fill`, `Press`
- [ ] Support: `Sleep`, `Wait`, `Scroll`, `Hover`
- [ ] Support: `Highlight`, `Unhighlight`, `Screenshot`

### Phase 4: Video Pipeline
- [ ] FFmpeg segment concatenation
- [ ] Consistent resolution across segments
- [ ] Smooth transitions between modes

### Phase 5: Narration (TTS)
- [ ] ElevenLabs integration
- [ ] Google TTS (gTTS) fallback
- [ ] `@voice` directive parsing
- [ ] `@narrate:before/during/after` modes
- [ ] Audio timing calculation
- [ ] FFmpeg audio mixing with video

### Phase 6: Polish
- [ ] `demorec validate` command
- [ ] `demorec voices` command  
- [ ] `demorec install` for browser setup
- [ ] Error messages with line numbers
- [ ] Progress output during recording
- [ ] SRT subtitle generation

### Phase 7: Advanced Features (Future)
- [ ] `Include` directive for reusable snippets
- [ ] `Hide`/`Show` for setup commands
- [x] Persistent terminal session across mode switches
- [x] Multiple named terminal sessions (`@mode terminal:name`)
- [ ] GIF output support
- [ ] Cursor/mouse visualization in browser
- [ ] Picture-in-picture mode

---

## Prior Art

- [charmbracelet/vhs](https://github.com/charmbracelet/vhs) - Terminal GIF recorder (inspiration)
- [fnando/demotape](https://github.com/fnando/demotape) - Ruby terminal recorder
- [Playwright](https://playwright.dev/) - Browser automation
- [xterm.js](https://xtermjs.org/) - Terminal emulator for the web

## License

MIT
