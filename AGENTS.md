# demorec Development Guide

Instructions for AI agents (and humans) working on the demorec codebase.

## Project Overview

**demorec** creates terminal and browser demo videos with narration. It supports
high-level vim primitives for code review videos (Open, Highlight, Goto, Close).

## Quick Reference

```bash
# Install
pip install -e ".[dev]"

# Pre-commit checks (run all before committing)
ruff check --fix src/ && ruff format src/ && pytest tests/ -q

# Quality checks
xenon --max-absolute C --max-modules A --max-average A src/demorec/
python scripts/check_function_length.py src/ --warn 8 --error 12
```

## Project Structure

```
src/demorec/
├── cli.py           # Click CLI (record, stage, preview, checkpoints)
├── parser.py        # .demorec script parsing
├── runner.py        # Recording orchestration
├── audio.py         # FFmpeg audio mixing, SRT generation
├── tts.py           # Text-to-speech (edge-tts)
├── preview.py       # Checkpoint verification
├── stage.py         # Vim stage direction calculator
├── checkpoints.py   # Checkpoint detection from commands
├── ttyd.py          # ttyd process lifecycle management
├── xterm.py         # xterm.js configuration wrapper
├── js/              # Static JS assets for xterm.js
│   ├── setup_terminal.js   # Full viewport + row targeting
│   ├── fit_to_rows.js      # Iterative font adjustment
│   ├── get_buffer_state.js # Buffer inspection
│   └── setup_container.js  # Simple container setup
└── modes/
    ├── browser.py           # Browser recording (Playwright)
    ├── terminal.py          # Terminal recording (ttyd)
    ├── terminal_commands.py # Command handlers + themes
    └── vim.py               # Vim primitives (VimCommandExpander)
```

## Code Quality Thresholds

| Check | Threshold | Command |
|-------|-----------|---------|
| Lint | Must pass | `ruff check src/` |
| Format | Must pass | `ruff format --check src/` |
| Complexity | Max C (11-20) | `xenon --max-absolute C --max-modules A --max-average A src/demorec/` |
| Function Length | Warn >8, Error >12 | `python scripts/check_function_length.py src/ --warn 8 --error 12` |
| File Length | Warn >200, Error >400 | `python scripts/check_file_length.py src/ --warn 200 --error 400` |

### Function Length Rules

Logic lines counted (excludes docstrings, comments, blanks, logging):
- ✓ **OK**: ≤8 lines (ideal)
- ⚠ **Warning**: 9-12 lines (consider refactoring)
- ✗ **Error**: >12 lines (must fix)

**Exemption marker** (use sparingly, requires justification):
```python
def complex_but_necessary():  # length-ok
    """Explain why this can't be split."""
    ...
```

### File Length Rules

Non-blank lines counted:
- ✓ **OK**: ≤200 lines (single responsibility)
- ⚠ **Warning**: 201-400 lines (consider splitting)
- ✗ **Error**: >400 lines (must split)

### Complexity Grades (Cyclomatic)

- **A** (1-5): Simple - target for most functions
- **B** (6-10): Low - acceptable
- **C** (11-20): Moderate - maximum allowed
- **D+** (21+): High - blocked by CI

## ⚠️ Threshold Policy

> **AI agents MUST NOT change quality thresholds without explicit human approval.**
>
> To request changes:
> 1. Show ALL functions exceeding thresholds
> 2. Explain why each cannot be reasonably refactored
> 3. Wait for human approval

## Refactoring Patterns

When functions exceed thresholds, use these patterns:

### 1. Dispatch Tables
Replace long if/elif chains:
```python
# Before
def handle(cmd):
    if cmd == "open": ...
    elif cmd == "close": ...

# After
HANDLERS = {"open": _handle_open, "close": _handle_close}
def handle(cmd):
    return HANDLERS[cmd]()
```

### 2. Extract Helpers
Break into focused sub-functions:
```python
# Before: 30-line function
def process():
    # parse input (10 lines)
    # transform data (10 lines)
    # format output (10 lines)

# After: 3 small functions
def process():
    data = _parse_input()
    result = _transform(data)
    return _format_output(result)
```

### 3. Class-Based State
For complex parsing/state management:
```python
class _Tokenizer:
    def __init__(self, text): ...
    def next_token(self): ...  # Small, focused method
```

## Key Design Patterns

### Vim Primitives
`VimCommandExpander` translates high-level commands to keystrokes:
- `Open "file.py"` → `vim file.py` + `:set number`
- `Highlight "10-20"` → `10G` + `V` + `20G`
- `Goto 50` → `50Gzz`
- `Close` → `Escape` + `:q!`

### Terminal Sizing
- `@terminal:rows N` - Set specific row count
- `@terminal:size large|medium|small|tiny` - Presets
- Font auto-adjusts via `term.fit()`

### Narration Timing
- `# @narrate:before "text"` - Before command
- `# @narrate:during "text"` - During command  
- `# @narrate:after "text"` - After command

## CI Pipeline

All checks must pass:
1. **Lint** - `ruff check src/`
2. **Format** - `ruff format --check src/`
3. **Tests** - `pytest` (Python 3.10, 3.11, 3.12)
4. **Complexity** - `xenon`
5. **Function Length** - `check_function_length.py`

## Common Commands

```bash
# Record a demo
demorec record script.demorec -o output.mp4

# Preview without recording
demorec preview script.demorec

# Calculate vim stage directions
demorec stage file.py "10-20,30-40" --rows 30

# Show all checkpoints
demorec checkpoints script.demorec
```
