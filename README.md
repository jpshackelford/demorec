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
```

Preview auto-detects "show moments" (visual selections in vim) and verifies that expected lines are visible:

```
[PASS] Checkpoint 1 (line 11): lines 6-8 visible
[PASS] Checkpoint 2 (line 33): lines 27-35 visible
Summary: 2/2 passed
```

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

### Mode Switching

```tape
@mode terminal               # Switch to terminal recording (default session)
@mode terminal:server        # Switch to named terminal session "server"
@mode terminal:client        # Switch to named terminal session "client"
@mode browser                # Switch to browser recording
```

**Persistent Sessions:** Terminal state (working directory, environment variables, command history) persists when switching between modes. Returning to the same terminal session reconnects to the existing PTY.

**Named Sessions:** Use `terminal:name` to create multiple independent terminal sessions (e.g., for server/client demos).

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

```tape
Output multi-terminal-demo.mp4

# Start a server in one terminal
@mode terminal:server
Type "npm start"
Enter
Sleep 2s

# Run client commands in another terminal
@mode terminal:client
Type "curl http://localhost:3000/api/status"
Enter
Sleep 1s

# Switch back to server to see the logged request
@mode terminal:server
# Terminal state is preserved - we see the server still running
Sleep 2s

# Back to client for another request
@mode terminal:client
Type "curl -X POST http://localhost:3000/api/data"
Enter
Sleep 1s
```

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
