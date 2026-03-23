#!/usr/bin/env python3
"""Check per-file coverage against baseline thresholds.

Features:
- Ratcheting: existing files cannot drop below their baseline coverage
- New files: must meet minimum threshold (default 80%) unless exempted
- Exemptions: files can be exempted with a reason in the baseline

Usage:
    # Check coverage against baseline
    python scripts/check_coverage.py

    # Update baseline with current coverage (ratchet up only)
    python scripts/check_coverage.py --update-baseline

    # Show coverage report without failing
    python scripts/check_coverage.py --report-only

Baseline file format (.coverage-baseline.json):
{
    "files": {
        "src/demorec/cli.py": {"min_coverage": 85.0},
        "src/demorec/runner.py": {"min_coverage": 62.0}
    },
    "exempt": {
        "src/demorec/__init__.py": "version-only module"
    },
    "new_file_threshold": 80.0
}
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# ANSI colors
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"
BOLD = "\033[1m"

BASELINE_FILE = Path(".coverage-baseline.json")
DEFAULT_NEW_FILE_THRESHOLD = 80.0
# Allow small variance in coverage (e.g., due to timing differences in async tests)
TOLERANCE = 0.5


def run_coverage_json() -> dict:
    """Run coverage json and return the parsed data."""
    result = subprocess.run(
        ["python", "-m", "coverage", "json", "-o", "-"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"{RED}Error running coverage json:{RESET}")
        print(result.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def load_baseline() -> dict:
    """Load baseline from file, or return empty baseline."""
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text())
    return {"files": {}, "exempt": {}, "new_file_threshold": DEFAULT_NEW_FILE_THRESHOLD}


def save_baseline(baseline: dict) -> None:
    """Save baseline to file."""
    BASELINE_FILE.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")


def get_file_coverage(cov_data: dict) -> dict[str, float]:
    """Extract per-file coverage percentages from coverage data."""
    result = {}
    for filepath, data in cov_data.get("files", {}).items():
        summary = data.get("summary", {})
        percent = summary.get("percent_covered", 0.0)
        result[filepath] = round(percent, 1)
    return result


def check_coverage(report_only: bool = False) -> bool:
    """Check coverage against baseline. Returns True if all checks pass."""
    cov_data = run_coverage_json()
    baseline = load_baseline()
    file_coverage = get_file_coverage(cov_data)

    new_threshold = baseline.get("new_file_threshold", DEFAULT_NEW_FILE_THRESHOLD)
    baseline_files = baseline.get("files", {})
    exempt_files = baseline.get("exempt", {})

    errors = []
    warnings = []

    print(f"\n{BOLD}Per-File Coverage Report{RESET}\n")
    print(f"{'File':<50} {'Current':>8} {'Baseline':>10} {'Status':>10}")
    print("-" * 82)

    for filepath, current in sorted(file_coverage.items()):
        # Check if exempt
        if filepath in exempt_files:
            reason = exempt_files[filepath]
            print(f"{filepath:<50} {current:>7.1f}% {'exempt':>10} {CYAN}exempt{RESET}")
            continue

        # Check if existing file (in baseline)
        if filepath in baseline_files:
            min_cov = baseline_files[filepath]["min_coverage"]
            # Allow small tolerance for variance between runs
            effective_min = min_cov - TOLERANCE
            if current < effective_min:
                status = f"{RED}FAIL{RESET}"
                errors.append(
                    f"{filepath}: coverage dropped from {min_cov}% to {current}%"
                )
            elif current > min_cov:
                status = f"{GREEN}IMPROVED{RESET}"
            else:
                status = f"{GREEN}OK{RESET}"
            print(f"{filepath:<50} {current:>7.1f}% {min_cov:>9.1f}% {status}")
        else:
            # New file - must meet new_file_threshold
            if current < new_threshold:
                status = f"{RED}FAIL{RESET}"
                errors.append(
                    f"{filepath}: new file has {current}% coverage "
                    f"(requires {new_threshold}%)"
                )
            else:
                status = f"{GREEN}NEW OK{RESET}"
            print(f"{filepath:<50} {current:>7.1f}% {new_threshold:>9.1f}%* {status}")

    print("-" * 82)
    print(f"* = new file threshold ({new_threshold}%)\n")

    # Print summary
    total = cov_data.get("totals", {}).get("percent_covered", 0)
    print(f"{BOLD}Total Coverage: {total:.1f}%{RESET}\n")

    if errors:
        print(f"{RED}{BOLD}Errors:{RESET}")
        for err in errors:
            print(f"  ✗ {err}")
        print()

    if warnings:
        print(f"{YELLOW}{BOLD}Warnings:{RESET}")
        for warn in warnings:
            print(f"  ⚠ {warn}")
        print()

    if report_only:
        return True

    return len(errors) == 0


def update_baseline() -> None:
    """Update baseline with current coverage (ratchet up only)."""
    cov_data = run_coverage_json()
    baseline = load_baseline()
    file_coverage = get_file_coverage(cov_data)

    baseline_files = baseline.setdefault("files", {})
    exempt_files = baseline.get("exempt", {})

    updated = []
    added = []

    for filepath, current in sorted(file_coverage.items()):
        if filepath in exempt_files:
            continue

        if filepath in baseline_files:
            old_min = baseline_files[filepath]["min_coverage"]
            if current > old_min:
                baseline_files[filepath]["min_coverage"] = current
                updated.append(f"{filepath}: {old_min}% -> {current}%")
        else:
            baseline_files[filepath] = {"min_coverage": current}
            added.append(f"{filepath}: {current}%")

    # Remove files that no longer exist
    removed = []
    for filepath in list(baseline_files.keys()):
        if filepath not in file_coverage:
            del baseline_files[filepath]
            removed.append(filepath)

    save_baseline(baseline)

    print(f"\n{BOLD}Baseline Updated{RESET}\n")

    if added:
        print(f"{GREEN}Added:{RESET}")
        for item in added:
            print(f"  + {item}")

    if updated:
        print(f"{CYAN}Updated (ratcheted up):{RESET}")
        for item in updated:
            print(f"  ↑ {item}")

    if removed:
        print(f"{YELLOW}Removed (files no longer exist):{RESET}")
        for item in removed:
            print(f"  - {item}")

    if not (added or updated or removed):
        print("No changes to baseline.")

    print(f"\nBaseline saved to {BASELINE_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Check per-file coverage thresholds")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Update baseline with current coverage (ratchet up only)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Show report without failing on threshold violations",
    )
    args = parser.parse_args()

    if args.update_baseline:
        update_baseline()
    else:
        success = check_coverage(report_only=args.report_only)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
