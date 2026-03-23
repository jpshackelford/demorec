# CI Quality Thresholds

This document tracks the current and target CI thresholds for code quality checks.
The CI was initially configured with relaxed thresholds to pass on existing code.
Gradually tighten these as the codebase improves.

## Current vs Target Thresholds

| Check | Current (Relaxed) | Target (Strict) | File to Edit |
|-------|-------------------|-----------------|--------------|
| **Lint** | Non-blocking (`\|\| true`) | Blocking | `.github/workflows/ci.yml` |
| **Format** | Non-blocking (`\|\| true`) | Blocking | `.github/workflows/ci.yml` |
| **Complexity (absolute)** | D (21-30) | C (11-20) | `.github/workflows/ci.yml` |
| **Complexity (modules)** | B (6-10) | A (1-5) | `.github/workflows/ci.yml` |
| **Complexity (average)** | B (6-10) | A (1-5) | `.github/workflows/ci.yml` |
| **Function Length (warn)** | 20 lines | 8 lines | `.github/workflows/ci.yml` |
| **Function Length (error)** | 65 lines | 12 lines | `.github/workflows/ci.yml` |

## How to Tighten Thresholds

### 1. Lint (Ruff)

**Current:**
```yaml
run: ruff check src/ || true
run: ruff format --check src/ || true
```

**Target:**
```yaml
run: ruff check src/
run: ruff format --check src/
```

**Fix existing issues:**
```bash
ruff check src/ --fix      # Auto-fix linting issues
ruff format src/           # Auto-format code
```

### 2. Cyclomatic Complexity (Xenon)

**Current:**
```yaml
run: xenon --max-absolute D --max-modules B --max-average B src/demorec/
```

**Target:**
```yaml
run: xenon --max-absolute C --max-modules A --max-average A src/demorec/
```

**Complexity grades:**
- A: 1-5 (simple)
- B: 6-10 (low)
- C: 11-20 (moderate)
- D: 21-30 (high)
- E: 31-40 (very high)
- F: 41+ (extremely high)

**Fix high complexity:** Break complex functions into smaller, focused functions.

### 3. Function Length

**Current:**
```yaml
run: python scripts/check_function_length.py src/ --warn 20 --error 65
```

**Target:**
```yaml
run: python scripts/check_function_length.py src/ --warn 8 --error 12
```

**Exemptions:** Add `# length-ok` comment on the `def` line to exempt specific functions:
```python
def complex_but_necessary_function():  # length-ok
    # This function is intentionally long because...
    ...
```

## Recommended Approach

1. **Phase 1:** Fix all lint/format issues (easiest - can be auto-fixed)
2. **Phase 2:** Reduce function lengths (refactor large functions)
3. **Phase 3:** Reduce complexity (extract helper functions, simplify logic)

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
