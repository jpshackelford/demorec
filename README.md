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

# @voice eleven:rachel

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

### Terminal Rows Directive

Set a specific number of terminal rows for consistent viewport sizing:

```tape
@terminal:rows 30

@mode terminal
Set Theme "Dracula"
Type "vim myfile.py"
Enter
```

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
@mode terminal               # Switch to terminal recording
@mode browser                # Switch to browser recording
```

### Terminal Commands

| Command | Description | Example |
|---------|-------------|---------|
| `Set Theme "<name>"` | Terminal theme | `Set Theme "Dracula"` |
| `Type "<text>"` | Type text with delay | `Type "echo hello"` |
| `Enter` | Press Enter | `Enter` |
| `Sleep <time>` | Pause | `Sleep 2s` or `Sleep 500ms` |
| `Ctrl+<key>` | Control sequence | `Ctrl+C` |
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
# Set the voice (ElevenLabs)
# @voice eleven:rachel

# Narration modes
# @narrate:before "Spoken before the next action"
# @narrate:during "Spoken while action runs"
# @narrate:after "Spoken after action completes"
```

**Available voices:** `rachel`, `adam`, `josh`, `bella`, `antoni`, `domi`, `elli`, `arnold`, `sam`

### Time Formats

- Seconds: `2s`, `1.5s`
- Milliseconds: `500ms`, `100ms`

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ELEVENLABS_API_KEY` | ElevenLabs API key for high-quality TTS |

If no API key is set, demorec falls back to Google TTS (gTTS).

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

# @voice eleven:adam

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

# @voice eleven:rachel

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
- [ ] Persistent terminal session across mode switches
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
