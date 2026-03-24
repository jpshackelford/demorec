# CI Quality Thresholds

This document tracks the current and target CI thresholds for code quality checks.
Gradually tighten these as the codebase improves.

## Current vs Target Thresholds

| Check | Current | Target (Strict) | Status |
|-------|---------|-----------------|--------|
| **Lint** | Blocking | Blocking | ✅ Enforced |
| **Format** | Blocking | Blocking | ✅ Enforced |
| **Complexity (absolute)** | C (11-20) | C (11-20) | ✅ Enforced |
| **Complexity (modules)** | A (1-5) | A (1-5) | ✅ Enforced |
| **Complexity (average)** | A (1-5) | A (1-5) | ✅ Enforced |
| **Function Length (warn)** | 11 lines | 8 lines | 🔄 Relaxed |
| **Function Length (error)** | 25 lines | 12 lines | 🔄 Relaxed |

## How to Tighten Thresholds

### 1. Lint (Ruff) ✅ Enforced

Lint and format checks are now blocking. All code must pass:
```bash
ruff check src/            # Linting
ruff format --check src/   # Formatting
```

**Fix issues:**
```bash
ruff check src/ --fix      # Auto-fix linting issues
ruff format src/           # Auto-format code
```

### 2. Cyclomatic Complexity (Xenon) ✅ Enforced

Complexity checks are now enforced at strict thresholds:
```bash
xenon --max-absolute C --max-modules A --max-average A src/demorec/
```

**Complexity grades:**
- A: 1-5 (simple)
- B: 6-10 (low)
- C: 11-20 (moderate)
- D: 21-30 (high) - **blocked**
- E: 31-40 (very high) - **blocked**
- F: 41+ (extremely high) - **blocked**

**Fix high complexity:** Break complex functions into smaller, focused functions using dispatch tables or helper functions.

### 3. Function Length 🔄 Relaxed

Function length thresholds have been relaxed to accommodate larger feature additions:
```bash
python scripts/check_function_length.py src/ --warn 11 --error 25
```

**Ultimate target** (not yet enforced):
```bash
python scripts/check_function_length.py src/ --warn 8 --error 12
```

**Exemptions:** Add `# length-ok` comment on the `def` line to exempt specific functions:
```python
def complex_but_necessary_function():  # length-ok
    # This function is intentionally long because...
    ...
```

## Refactoring Techniques Used

1. **Dispatch tables**: Replace long if/elif chains with dictionaries mapping commands to handler functions
2. **Extract helper functions**: Break large functions into smaller focused helpers
3. **Class-based state**: Use classes like `_Tokenizer` to manage complex parsing state
4. **Phase-based methods**: Split pipeline functions like `run()` into `_run_*_phase()` methods

## Tracking Progress

Run these commands locally to see current violations:

```bash
# Lint issues
ruff check src/

# Format issues  
ruff format --check src/

# Complexity report
radon cc src/demorec/ -a -s

# Function length report
python scripts/check_function_length.py src/ --all
```
