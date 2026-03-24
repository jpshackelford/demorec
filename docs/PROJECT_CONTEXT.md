# Demo Recording Tools: Project Context & Background

## Purpose of This Document

This document provides context for an AI agent working on the `jpshackelford/demorec` project. It covers the evolution from separate skills in `.openhands` to the unified `demorec` CLI, key learnings, and next steps.

---

## Part 1: Background - The `.openhands` Skills

### Repository: `jpshackelford/.openhands`

This repository contains OpenHands skills (microagents) that teach agents how to perform specific tasks. Two skills are relevant to demo recording:

### 1. `terminal-recording` Skill (Merged - PR #3)

**Purpose:** Record terminal/CLI demos for PR demonstrations using VHS by Charmbracelet.

**Key Components:**
- `SKILL.md` - Comprehensive documentation with VHS commands, themes, troubleshooting
- `scripts/narrated_tape.py` - Python tool to add AI narration to VHS recordings
- `examples/demo_narrated.tape` - Example tape file with narration macros

**What It Does:**
- Uses VHS (Go-based terminal recorder) to create GIF/video recordings
- Supports `.tape` DSL files that script terminal interactions
- Adds AI narration via ElevenLabs TTS with custom macros (`@narrate:before`, `@narrate:during`, `@narrate:after`)
- Generates closed captions/subtitles

**Commits & Key Learnings:**

| Commit | Learning |
|--------|----------|
| `032c683` - Add terminal-recording skill | Base VHS workflow: install ttyd, write .tape files, render with VHS |
| `fffdc7b` - Container troubleshooting | **Critical:** VHS chromium sandbox fails in containers. Workaround: use Docker VHS image or switch to bash shell |
| `e837abf` - AI narration with ElevenLabs | Narration macros parsed from comments, audio generated, then mixed with FFmpeg |
| `58f0eb3` - Closed caption support | Soft subtitles via FFmpeg, auto-split long captions for readability |
| `3379e62` - Auto-split captions | Captions > 42 chars split at word boundaries for better UX |

**Discovered Limitations:**
- VHS requires ttyd + chromium - problematic in sandboxed/container environments
- Terminal-only - can't record browser interactions
- Two-pass workflow: generate video, then mix audio separately

### 2. `webtape` Skill (Open PR #4 - Not Merged)

**Purpose:** Record web/browser demos using Playwright with a VHS-like DSL.

**Key Components:**
- `webtape.py` - ~550 line Python CLI
- `scripts/tts.py` - TTS integration (ElevenLabs + gTTS fallback)
- Example `.webtape` files

**What It Does:**
- Uses Playwright for browser automation and screenshot capture
- Custom `.webtape` DSL inspired by VHS
- Supports: Navigate, Click, Type, Fill, Press, Sleep, Wait, Scroll, Hover, Highlight
- Same narration macro system as terminal-recording

**Why Not Merged:** This work is being superseded by `demorec` which unifies both terminal and browser recording.

### 3. PS1JSON Troubleshooting (Open PR #5)

**The Problem:** When recording in OpenHands environments, the zsh `precmd` hook outputs JSON tracking data (`###PS1JSON###...###PS1END###`) that appears in recordings.

**The Fix:**
```tape
Set Shell "bash"
Hide
Type "export PS1='$ ' && export PROMPT_COMMAND='' && unset -f precmd preexec 2>/dev/null; clear"
Enter
Show
```

**Learning:** Always use bash (not zsh) and reset the prompt in a hidden block before recording in OpenHands sandboxes.

---

## Part 2: The Vision - `demorec`

### Repository: `jpshackelford/demorec`

**Description:** "Record CLI and web-based demos from a single script"

### Why Unify?

Real-world product demos often require both terminal AND browser:
- Start a server via CLI → show the web UI
- Run a build command → verify results in browser  
- Configure via terminal → interact with the app

**Before:** Two separate tools, two DSLs, manual video stitching
**After:** One `.demorec` script, one CLI, seamless mode switching

### The Unified DSL

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
```

### Architecture

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
                         │ FFmpeg concat + TTS mix
                         ▼
                    demo.mp4 (final)
```

**Key Insight:** Both terminal AND browser rendering use Playwright. Terminal segments render via xterm.js in a headless browser, enabling seamless video concatenation with consistent dimensions.

---

## Part 3: Current State of `demorec`

### Repository Structure

```
jpshackelford/demorec/
├── src/demorec/
│   ├── __init__.py
│   ├── cli.py          # Click-based CLI: record, validate, voices
│   ├── parser.py       # DSL parser for .demorec files
│   ├── runner.py       # Orchestrates segment recording
│   ├── tts.py          # TTS integration (ElevenLabs + Edge TTS)
│   └── modes/
│       ├── __init__.py
│       ├── terminal.py # Terminal recording via xterm.js + ttyd
│       └── browser.py  # Browser recording via Playwright
├── examples/
├── pyproject.toml
└── README.md
```

### What's Working (as of commit `419635f`)

✅ **Phase 1: Core Infrastructure**
- Project structure with `pyproject.toml` (uv-compatible)
- Click CLI entry point (`demorec record`, `demorec validate`, `demorec voices`)
- DSL parser for `.demorec` files
- Segment planner (splits script by `@mode` switches)

✅ **Phase 2: Terminal Recording**
- xterm.js HTML template with theme support
- Terminal runner using Playwright
- Full PTY support via ttyd (real command execution)
- Supports: `Type`, `Enter`, `Sleep`, `Ctrl+X`, `Escape`
- ANSI color and styling verified
- **PS1JSON artifacts automatically cleaned** (no user action needed)

✅ **Phase 3: Browser Recording**
- `modes/browser.py` fully implemented
- Supports: Navigate, Click, Type, Fill, Press, Sleep, Wait, Scroll, Hover, Highlight, Screenshot
- Timestamp tracking for narration sync

✅ **Phase 4: Video Pipeline**
- FFmpeg segment concatenation working
- Consistent resolution across terminal/browser segments
- Smooth transitions between modes

✅ **Phase 5: Audio Mixing**
- TTS audio timing calculation with command timestamps
- FFmpeg audio mixing with `adelay` filter for precise placement
- **Fixed:** `normalize=0:dropout_transition=0` for consistent volume across sequential narrations
- Sync narration with actions using `@narrate:before/during/after`

✅ **Phase 6: Polish**
- `demorec install` command (Playwright browser setup)
- Error messages with line numbers
- Progress output during recording
- **SRT subtitle generation** - auto-generates `.srt` file alongside video
- Caption splitting at 42 chars for readability

✅ **TTS Integration**
- ElevenLabs as primary TTS (44.1kHz, paid)
- Edge TTS as free fallback (24kHz)
- `@voice` and `@narrate:*` macro parsing

### What's Not Yet Complete

🔲 **Phase 7: Advanced (Future)**
- `Include` directive for reusable snippets
- Persistent terminal session across mode switches
- GIF output support
- Cursor/mouse visualization
- Embedded subtitles (currently soft subs via separate .srt file)

---

## Part 4: Key Learnings to Carry Forward

### From `terminal-recording` Skill

1. **Container Sandbox Issues:** VHS's chromium sandbox fails in containers. Solution: use Playwright's built-in browser management instead of VHS.

2. **OpenHands PS1JSON:** ~~Always use bash and reset prompt in hidden block~~ **Now automatic!** The terminal recorder cleans PS1JSON artifacts by clearing `PROMPT_COMMAND`, `BASH_ENV`, `ENV`, and `BASH_FUNC_*` variables in the child process. Users don't need to do anything.

3. **Narration Timing:** Three modes work well:
   - `@narrate:before` - speak, then action (for introductions/announcements)
   - `@narrate:during` - action + speech in parallel
   - `@narrate:after` - action, then speak (for explanations/descriptions)

4. **Caption Splitting:** Auto-split captions at word boundaries when > 42 chars for readability.

5. **TTS Caching:** Cache generated audio to avoid redundant API calls during iterative development.

### From `webtape` Skill

1. **Highlight Action:** Visual highlighting (`Highlight "#selector"`) helps viewers follow along.

2. **Wait vs Sleep:** `Wait` for element appearance is more reliable than hardcoded `Sleep`.

3. **gTTS Fallback:** Google TTS (gTTS) works as free fallback but quality is lower than ElevenLabs.

### From `demorec` Development

1. **Unified Rendering:** Using Playwright for BOTH terminal (xterm.js) and browser ensures consistent video dimensions and easy concatenation.

2. **ttyd for Real PTY:** xterm.js alone is just a renderer. Connect to ttyd for actual shell execution.

3. **Edge TTS:** Microsoft Edge TTS is free and higher quality than gTTS - good middle ground.

4. **FFmpeg Audio Mixing for Sequential Clips:** When mixing non-overlapping narration clips, use `amix=inputs=N:normalize=0:dropout_transition=0` to prevent volume fluctuations. Without this, later clips sound louder as earlier clips end.

5. **Vim Scrolling in Demos:** When jumping to a line in vim, use `zt` after `NG` to scroll that line to the top of screen:
   ```tape
   Type "27G"   # Go to line 27
   Type "zt"    # Scroll line 27 to top of screen
   Type "V"     # Start visual line mode
   Type "35G"   # Extend selection to line 35
   ```
   Other options: `zz` (center), `zb` (bottom).

6. **Narration Timing Best Practices:**
   | Scenario | Directive | Example |
   |----------|-----------|---------|
   | Announce what you'll do | `@narrate:before` | "Let's scroll to the API methods" |
   | Describe what's visible | `@narrate:after` | "Here's the User dataclass with four fields" |
   | Explain during action | `@narrate:during` | Background explanation while typing |

7. **Debugging Recorded Videos:** Extract frames at specific timestamps to inspect:
   ```bash
   ffmpeg -i video.mp4 -ss 30 -vframes 1 frame_30s.png
   ```

8. **Terminal Size/Row Control - The VHS Solution:**

   **The Problem:** Users want to control how many rows are visible in terminal recordings (e.g., 24 rows for classic look, 50 for more content). The challenge is keeping xterm.js and the underlying PTY synchronized.

   **What We Learned from VHS:**

   VHS uses a elegant solution: `term.fit()` from xterm.js's fit addon handles BOTH:
   1. Calculating proper rows/cols based on viewport and font settings
   2. Triggering an `onResize` event that ttyd catches and propagates to the PTY

   **How It Works:**
   
   ```
   term.fit() called
        │
        ▼
   xterm.js calculates rows/cols
        │
        ▼
   onResize event fired ──────► ttyd JavaScript client
        │                               │
        ▼                               ▼
   xterm.js resized              WebSocket RESIZE_TERMINAL
        │                               │
        ▼                               ▼
   Video shows correct rows      ttyd server receives message
                                        │
                                        ▼
                                 ioctl(TIOCSWINSZ) updates PTY
   ```

   **The Solution (VHS-style):**
   ```javascript
   // 1. Set font options
   term.options.fontSize = newFontSize;
   term.options.fontFamily = fontFamily;
   term.options.lineHeight = lineHeight;
   
   // 2. Call fit() - this does everything!
   term.fit();  // Calculates rows, resizes xterm, syncs PTY via WebSocket
   
   // 3. Read back actual dimensions
   const rows = term.rows;  // PTY is already synced
   ```

   **Why This Is Better Than Our Previous Approach:**
   - ❌ Old: `window.dispatchEvent('resize')` + manual `stty rows X cols Y`
   - ✅ New: `term.fit()` handles both in one call via ttyd's WebSocket protocol

   **Key Files in ttyd:**
   - `html/src/components/terminal/xterm/index.ts:184-189`: Catches `onResize`, sends `RESIZE_TERMINAL`
   - `src/protocol.c:320-324`: Server receives message, calls `pty_resize()`
   - `src/pty.c:155-156`: Uses `ioctl(TIOCSWINSZ)` to update actual PTY

   **UX Decision:** Use named presets instead of raw row counts:
   ```
   @terminal:size large   # ~24 rows, classic terminal
   @terminal:size medium  # ~36 rows, balanced
   @terminal:size small   # ~44 rows, default density
   @terminal:size tiny    # ~50 rows, maximum content
   ```

9. **Playwright device_scale_factor:** When recording at 1280x720, use `device_scale_factor=1` (not 2). A scale factor of 2 causes xterm.js to render at 2x resolution, making characters appear half-sized and doubling the apparent row count. This was a major source of terminal size mismatch bugs.

---

## Part 5: Next Steps for `demorec`

### Immediate Priority: Browser Mode

Implement `modes/browser.py` to support:
```python
# Core actions needed:
Navigate(url)       # playwright.goto()
Click(selector)     # playwright.click()
Type(selector, text) # playwright.type() with delay
Fill(selector, text) # playwright.fill() instant
Press(key)          # playwright.press()
Sleep(duration)     # asyncio.sleep()
Wait(selector)      # playwright.wait_for_selector()
Scroll(direction, amount)
Hover(selector)
Highlight(selector) # inject CSS border
Screenshot(filename)
```

### Then: Video Pipeline

1. Record each segment to `segment_N.mp4`
2. Create FFmpeg concat demuxer file
3. Concatenate with consistent resolution
4. Mix TTS audio track

### Testing Strategy

1. Create test `.demorec` files for each mode
2. Test mode switching (terminal → browser → terminal)
3. Test narration sync
4. Test in OpenHands sandbox (verify PS1JSON handling)

---

## Part 6: Future Skill - `demorec` Skill

Once `demorec` is complete, create a new skill in `jpshackelford/.openhands`:

```
skills/demorec/
├── SKILL.md          # Full documentation
├── README.md
├── examples/
│   ├── cli-demo.demorec
│   ├── webapp-demo.demorec
│   └── fullstack-demo.demorec
└── templates/
    ├── bugfix.demorec
    └── feature.demorec
```

**Triggers:**
- "record a demo"
- "create a video demo"
- "demonstrate this feature"
- "show this working"
- "PR demo"

**The skill will:**
1. Help agents install `demorec` (`uv tool install demorec` or `pip install demorec`)
2. Provide templates for common demo scenarios
3. Guide writing `.demorec` scripts
4. Handle OpenHands-specific issues (PS1JSON, container sandboxes)
5. Publish/embed demos in PRs

---

## Part 7: How to Showcase Current Work

### Demo 1: Terminal Recording (Working Today)

```bash
# Clone and install
git clone https://github.com/jpshackelford/demorec
cd demorec
uv sync

# Create a simple terminal demo
cat > hello.demorec << 'EOF'
Output hello.mp4
Set Width 800
Set Height 400

@mode terminal
Set Theme "Dracula"

Type "echo 'Hello from demorec!'"
Enter
Sleep 2s

Type "ls -la"
Enter
Sleep 2s
EOF

# Record it
uv run demorec record hello.demorec
```

### Demo 2: With Narration (Requires ELEVENLABS_API_KEY)

```bash
cat > narrated.demorec << 'EOF'
Output narrated.mp4
Set Width 800
Set Height 400

# @voice eleven:rachel

@mode terminal
Set Theme "Dracula"

# @narrate:before "Welcome to demorec, the unified demo recorder."
Type "echo 'Recording terminal and browser demos'"
Enter
Sleep 2s

# @narrate:after "That's all there is to it!"
EOF

ELEVENLABS_API_KEY=your_key uv run demorec record narrated.demorec
```

### Demo 3: Validate Without Recording

```bash
uv run demorec validate my-demo.demorec
# Shows segment breakdown and validation results
```

### What to Show in a PR/Presentation

1. **The Problem:** Separate tools for terminal vs browser demos, manual stitching
2. **The Solution:** Single `.demorec` DSL with `@mode` switching
3. **Working Demo:** Terminal recording with AI narration
4. **Architecture:** Playwright-based unified rendering
5. **Roadmap:** Browser mode → video pipeline → full release

---

## Summary

| Repo | Purpose | Status |
|------|---------|--------|
| `jpshackelford/.openhands` | Skills teaching agents to record demos | `terminal-recording` merged, `webtape` open PR |
| `jpshackelford/demorec` | Unified CLI tool combining both | Terminal MVP working, browser mode in progress |

**The Goal:** A single `demorec` CLI that records seamless terminal + browser demos with AI narration, then a skill that teaches agents to use it effectively.
