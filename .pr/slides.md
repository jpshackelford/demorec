---
marp: true
theme: default
paginate: false
---

# OpenHands CLI Primitives

**High-level commands for demo recording**

---

## The Problem

- Recording OpenHands CLI demos requires complex keystroke sequences
- Manual typing of `openhands`, waiting for startup, sending prompts
- Hard to time correctly — AI responses vary in length
- Ctrl+L for multiline, Ctrl+J to submit, Ctrl+Q to quit...

---

## The Solution: CLI Primitives

Demorec now supports high-level OpenHands commands:

| Command | What it does |
|---------|-------------|
| `Install` | Installs OpenHands CLI via uv |
| `Start` | Launches the CLI and waits for ready |
| `Prompt "text"` | Sends a prompt to the AI |
| `WaitForReady` | Waits for AI to finish responding |
| `Quit` | Exits the CLI cleanly |

---

## Example Script

```tape
@mode terminal:openhands

Install
Start
Prompt "Tell me a dad joke"
WaitForReady
Quit
```

One line per action. No keystroke details.

---

## Let's See It In Action

*Live terminal demo*

---

# OpenHands CLI Primitives

**High-level commands for demo recording**

github.com/OpenHands/demorec

