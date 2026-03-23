# demorec Development Guide

This file contains instructions for AI agents (and humans) working on the demorec codebase.

## Project Overview

demorec is a terminal and browser recording tool that creates demo videos with narration.
It supports high-level primitives for vim-based code review videos.

## Development Tools Summary

| Tool | Purpose | Command |
|------|---------|---------|
| **pytest** | Testing | `pytest tests/` |
| **ruff** | Linting + import sorting | `ruff check src/ tests/` |
| **xenon** | Complexity threshold enforcement | `xenon --max-absolute C --max-modules A --max-average A src/demorec/` |
| **check_function_length.py** | Function line count | `python scripts/check_function_length.py src/ --warn 15 --error 25` |

## Standard Development Workflow

Before committing changes, run:
```bash
# 1. Lint and auto-fix
ruff check --fix src/ tests/

# 2. Run tests
pytest tests/

# 3. Check complexity
xenon --max-absolute C --max-modules A --max-average A src/demorec/

# 4. Check function lengths
python scripts/check_function_length.py src/ --warn 15 --error 25
```

## Quick Start

```bash
# Install in development mode
pip install -e ".[dev]"

# Run all tests
pytest tests/

# Lint code
ruff check src/ tests/

# Run the CLI
demorec --help
demorec record script.demorec
```

## Project Structure

```
src/demorec/
├── __init__.py      # Package version
├── __main__.py      # Entry point for `python -m demorec`
├── cli.py           # Click CLI commands (record, stage, preview, checkpoints)
├── parser.py        # Script parsing (.demorec files)
├── runner.py        # Recording orchestration, audio mixing, SRT generation
├── tts.py           # Text-to-speech integration (edge-tts)
├── preview.py       # Checkpoint verification system
├── stage.py         # Stage direction calculator for vim
└── modes/           # Recording mode implementations
    ├── __init__.py
    ├── browser.py   # Browser recording with Playwright
    ├── terminal.py  # Terminal recording with ttyd
    └── vim.py       # Vim command primitives (Open, Highlight, Close, Goto)

tests/
├── conftest.py      # Pytest config
├── test_parser.py   # Script parsing tests
├── test_runner.py   # Runner tests
├── test_tts.py      # TTS tests
└── ...
```

## Code Quality Thresholds

**Complexity (enforced by xenon):**
- Individual functions: max complexity C (11-20)
- Module average: A
- Absolute max: C

**Function Length (enforced by check_function_length.py):**
- ✓ OK: ≤15 logic lines
- ⚠ WARNING: 16-25 logic lines
- ✗ ERROR: >25 logic lines

**⚠️ THRESHOLD CHANGE POLICY:**
> AI agents **MUST NOT** change these thresholds without explicit human approval.
>
> To request a threshold change:
> 1. Run the checker and present ALL functions exceeding the current thresholds
> 2. Explain why each function cannot be reasonably refactored
> 3. Wait for explicit human approval before modifying thresholds

## Key Design Patterns

### Recording Modes

Each recording mode (browser, terminal) implements:
- `record_segment()` - Records a segment of the demo
- Mode-specific setup and teardown

### Vim Primitives

High-level vim commands are expanded by `VimCommandExpander`:
- `Open "file.py"` → vim command with line numbers
- `Highlight "10-20"` → goto + visual mode selection
- `Goto 50` → jump to line with centering
- `Close` → exit vim cleanly

### Terminal Sizing

Terminal size is controlled via:
- `@terminal:rows N` - Set to specific row count
- `@terminal:size large|medium|small|tiny` - Preset sizes
- Font size is adjusted automatically to achieve target rows

### Narration Timing

Narration can be placed:
- `# @narrate:before "text"` - Before command
- `# @narrate:during "text"` - During command
- `# @narrate:after "text"` - After command

Audio is mixed at correct timestamps using ffmpeg.

## Common Tasks

### Adding a New CLI Command

1. Add command to `src/demorec/cli.py`
2. Add tests to `tests/`
3. Run `pytest tests/ && ruff check src/`

### Adding a New Vim Primitive

1. Add generator function in `src/demorec/modes/vim.py`
2. Register in `VimCommandExpander.expand_command()`
3. Add tests

### Running a Demo Recording

```bash
# Basic recording
demorec record script.demorec -o output.mp4

# Preview checkpoints without recording
demorec preview script.demorec

# Calculate stage directions
demorec stage file.py "10-20,30-40" --rows 30
```

## Continuous Integration

CI runs on every PR:
1. **Lint** - `ruff check src/`
2. **Tests** - `pytest tests/` (Python 3.10, 3.11, 3.12)
3. **Complexity** - `xenon --max-absolute C ...`
4. **Function Length** - `python scripts/check_function_length.py ...`

All checks must pass before merging.
