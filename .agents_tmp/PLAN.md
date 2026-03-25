# 1. OBJECTIVE

Enhance the `demorec preview` command to capture **frame-by-frame snapshots** of the terminal buffer (text) or browser page (screenshot) for every step in the script. This provides AI agents with detailed visibility into what is rendered at each step for debugging and verification purposes.

# 2. CONTEXT SUMMARY

## Repository Structure
- **CLI entry point**: `src/demorec/cli.py` - Contains the `preview` command
- **Preview module**: `src/demorec/preview.py` - `TerminalPreviewer` class
- **xterm utilities**: `src/demorec/xterm.py` - `get_buffer_state()` function returns terminal visible lines
- **Browser recorder**: `src/demorec/modes/browser.py` - `BrowserRecorder` class with `page.screenshot()` 

## Current Behavior
- `demorec preview` only captures screenshots at auto-detected checkpoints (visual selections)
- Reports pass/fail status but misses most visual state during script execution
- Only processes terminal segments, not browser segments
- Has `--output-dir` option but only uses it for checkpoint screenshots

## Key Dependencies
- Playwright (async) for browser/terminal interaction
- `get_buffer_state()` returns `BufferState` with `visible_lines` (list of strings)
- Existing timing is tracked per-command in runner.py

## Constraints
- Frame naming: `frame_{number}_{secs}.txt` or `.png`
- Capture timing: **immediately before** the next command executes
- Terminal → `.txt` files, Browser → `.png` files

# 3. APPROACH OVERVIEW

**Chosen Approach**: Extend `TerminalPreviewer` into a more general `ScriptPreviewer` that handles both terminal and browser modes with frame-by-frame capture.

**Rationale**: The existing preview infrastructure already handles command execution and buffer state retrieval. We extend it to:
1. Support both modes (terminal and browser)
2. Capture frames at every command execution (not just checkpoints)
3. Track elapsed time for frame naming
4. Output to user-specified directory with the requested naming convention

**Key Design Decisions**:
1. Capture happens **before** each command executes (giving previous command time to render)
2. Initial frame captured before first command (shows initial state)
3. Frame numbering is 1-based and zero-padded to 4 digits (0001, 0002, ...)
4. Time formatting: seconds with 2 decimal places, zero-padded to 6 chars (000.00, 001.25, 012.75)

# 4. IMPLEMENTATION STEPS

## Phase 1: Clone Repository and Set Up Environment

### Step 1.1: Clone the repository
- **Goal**: Get the codebase locally
- **Method**: `git clone https://github.com/jpshackelford/demorec.git`

### Step 1.2: Set up development environment
- **Goal**: Install dependencies
- **Method**: Use `uv` to install dependencies per project's pyproject.toml
- **Reference**: `pyproject.toml`, `uv.lock`

---

## Phase 2: Modify CLI Interface

### Step 2.1: Update `--output-dir` behavior in preview command
- **Goal**: When `--output-dir` is specified, enable frame-by-frame capture mode
- **Method**: Add logic to pass output_dir to previewer and enable frame capture
- **Reference**: `src/demorec/cli.py` - `preview()` function

### Step 2.2: Add `--frames` flag (optional enhancement)
- **Goal**: Explicitly enable/disable frame capture (default: enabled when output-dir set)
- **Method**: Add `--frames/--no-frames` option to CLI
- **Reference**: `src/demorec/cli.py`

---

## Phase 3: Extend Preview Module for Frame Capture

### Step 3.1: Add frame capture infrastructure to `TerminalPreviewer`
- **Goal**: Track frame number and elapsed time during preview
- **Method**: 
  - Add `_frame_counter` and `_start_time` instance variables
  - Create `_capture_frame()` method that:
    - Gets buffer state (terminal) or takes screenshot (browser)
    - Formats filename as `frame_{NNNN}_{SSS.ss}.{ext}`
    - Writes to output directory
- **Reference**: `src/demorec/preview.py`

### Step 3.2: Modify command execution loop to capture frames
- **Goal**: Capture frame BEFORE each command executes
- **Method**:
  - In `_run_commands()`, call `_capture_frame()` before each command dispatch
  - Capture initial frame before the loop starts (frame_0001)
- **Reference**: `src/demorec/preview.py` - `_run_commands()` method

### Step 3.3: Implement terminal frame capture (.txt)
- **Goal**: Save terminal buffer state as text file
- **Method**:
  - Use `get_buffer_state()` to get visible lines
  - Join lines with newlines and write to `.txt` file
- **Reference**: `src/demorec/preview.py`, `src/demorec/xterm.py`

---

## Phase 4: Add Browser Mode Support to Preview

### Step 4.1: Create browser preview capability
- **Goal**: Enable preview command to process browser segments
- **Method**:
  - Extract browser setup logic from `BrowserRecorder` 
  - Add `BrowserPreviewer` class or extend `TerminalPreviewer` to `ScriptPreviewer`
  - Handle `@mode browser` segments
- **Reference**: `src/demorec/preview.py`, `src/demorec/modes/browser.py`

### Step 4.2: Implement browser frame capture (.png)
- **Goal**: Capture browser screenshots at each step
- **Method**:
  - Use Playwright's `page.screenshot(path=...)` 
  - Save as `.png` with proper frame naming
- **Reference**: `src/demorec/modes/browser.py` - `_cmd_screenshot()`

### Step 4.3: Handle mode switching during preview
- **Goal**: Support scripts that switch between terminal and browser modes
- **Method**:
  - Process ALL segments in order (not just first terminal segment)
  - Maintain frame counter across mode switches
  - Maintain elapsed time across mode switches
- **Reference**: `src/demorec/cli.py` - `_get_terminal_segment()` needs to be removed/refactored

---

## Phase 5: Frame Naming and File Output

### Step 5.1: Implement frame number formatting
- **Goal**: Zero-padded 4-digit frame numbers (0001, 0002, ...)
- **Method**: `f"frame_{frame_num:04d}_{elapsed:06.2f}.{ext}"`
- **Reference**: `src/demorec/preview.py`

### Step 5.2: Implement elapsed time formatting
- **Goal**: Seconds with 2 decimal places (000.00, 001.25, 012.75)
- **Method**: Track start time, calculate elapsed for each frame
- **Reference**: `src/demorec/preview.py`

### Step 5.3: Ensure output directory is created
- **Goal**: Create output directory if it doesn't exist
- **Method**: Use `Path.mkdir(parents=True, exist_ok=True)`
- **Reference**: `src/demorec/preview.py` - `_setup_screenshot_dir()`

---

## Phase 6: Testing and Documentation

### Step 6.1: Add unit tests for frame capture
- **Goal**: Verify frame naming, capture logic, and file output
- **Method**: Create tests in `tests/test_preview.py`
- **Reference**: `tests/` directory

### Step 6.2: Add integration test with sample script
- **Goal**: Verify end-to-end frame capture works
- **Method**: Create test script with terminal and browser modes
- **Reference**: `examples/` directory

### Step 6.3: Update README and CLI help
- **Goal**: Document new frame capture functionality
- **Method**: Update README.md preview section and CLI help strings
- **Reference**: `README.md`, `src/demorec/cli.py`

# 5. TESTING AND VALIDATION

## Success Criteria

1. **Frame capture works for terminal mode**:
   - Running `demorec preview script.demorec --output-dir ./frames` produces `.txt` files
   - Files are named `frame_0001_000.00.txt`, `frame_0002_001.25.txt`, etc.
   - Each file contains the terminal buffer state at that moment

2. **Frame capture works for browser mode**:
   - Browser segments produce `.png` screenshot files
   - Files follow same naming convention with `.png` extension

3. **Timing is correct**:
   - Frames are captured BEFORE each command executes
   - First frame (0001) shows initial state
   - Elapsed time increases appropriately

4. **Mode switching works**:
   - Scripts with both terminal and browser produce mixed `.txt` and `.png` files
   - Frame numbering is continuous across mode switches

## Validation Steps

1. **Manual test with sample script**:
   ```bash
   # Create test script that uses both modes
   cat > test.demorec << 'EOF'
   Output test.mp4
   @mode terminal
   Type "echo hello"
   Enter
   Sleep 1s
   @mode browser
   Navigate "https://example.com"
   Sleep 2s
   EOF
   
   # Run preview with frame capture
   demorec preview test.demorec --output-dir ./frames --rows 30
   
   # Verify output
   ls -la ./frames/
   # Should see: frame_0001_000.00.txt, frame_0002_000.XX.txt, frame_0003_001.XX.png, etc.
   ```

2. **Verify existing preview functionality still works**:
   - Checkpoint detection and verification should still function
   - Screenshot-on-error should still work alongside frame capture

3. **Run existing test suite**:
   ```bash
   uv run pytest tests/ -v
   ```
