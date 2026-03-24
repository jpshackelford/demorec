#!/usr/bin/env python3
"""Check file lengths against configurable thresholds.

Usage:
    python scripts/check_file_length.py src/ --warn 300 --error 500
"""

import argparse
import sys
from pathlib import Path


def count_lines(file_path: Path) -> int:
    """Count non-blank lines in a file."""
    try:
        with open(file_path) as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def check_files(
    directory: Path,
    warn_threshold: int,
    error_threshold: int,
    show_all: bool = False,
) -> tuple[list, list, list]:
    """Check all Python files in directory."""
    ok_files = []
    warn_files = []
    error_files = []

    for py_file in sorted(directory.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue

        lines = count_lines(py_file)
        rel_path = py_file.relative_to(directory.parent)

        if lines > error_threshold:
            error_files.append((rel_path, lines))
        elif lines > warn_threshold:
            warn_files.append((rel_path, lines))
        else:
            ok_files.append((rel_path, lines))

    return ok_files, warn_files, error_files


def main():
    parser = argparse.ArgumentParser(description="Check Python file lengths")
    parser.add_argument("directory", type=Path, help="Directory to check")
    parser.add_argument(
        "--warn", "-w", type=int, default=300,
        help="Warning threshold (default: 300 lines)"
    )
    parser.add_argument(
        "--error", "-e", type=int, default=500,
        help="Error threshold (default: 500 lines)"
    )
    parser.add_argument(
        "--all", "-a", action="store_true",
        help="Show all files sorted by length"
    )

    args = parser.parse_args()

    if not args.directory.exists():
        print(f"Error: {args.directory} does not exist")
        sys.exit(2)

    ok_files, warn_files, error_files = check_files(
        args.directory, args.warn, args.error, args.all
    )

    if args.all:
        all_files = ok_files + warn_files + error_files
        all_files.sort(key=lambda x: -x[1])
        print("All files sorted by length:")
        print(f"{'File':<50} {'Lines':>6}")
        print("-" * 58)
        for path, lines in all_files:
            status = "✗" if lines > args.error else ("⚠" if lines > args.warn else "✓")
            print(f"{status} {str(path):<48} {lines:>6}")
        print()

    if error_files:
        print(f"\nERRORS - Must fix (>{args.error} lines): {len(error_files)}")
        print(f"{'File':<50} {'Lines':>6}")
        print("-" * 58)
        for path, lines in sorted(error_files, key=lambda x: -x[1]):
            print(f"{str(path):<50} {lines:>6}")

    if warn_files:
        print(f"\nWARNINGS - Consider splitting (>{args.warn} lines): {len(warn_files)}")
        print(f"{'File':<50} {'Lines':>6}")
        print("-" * 58)
        for path, lines in sorted(warn_files, key=lambda x: -x[1]):
            print(f"{str(path):<50} {lines:>6}")

    print(f"\nSummary:")
    print(f"  ✓ OK ({args.warn} lines or less): {len(ok_files)}")
    print(f"  ⚠ Warnings (>{args.warn} lines): {len(warn_files)}")
    print(f"  ✗ Errors (>{args.error} lines): {len(error_files)}")

    if error_files:
        print(f"\nFAILED: {len(error_files)} file(s) exceed {args.error} lines.")
        sys.exit(1)

    print("\nPASSED: All files within limits.")
    sys.exit(0)


if __name__ == "__main__":
    main()
