#!/usr/bin/env python3
"""Generate a consolidated quality report for PR comments.

Combines coverage, complexity, and function length metrics into a single
concise, actionable markdown report.

Usage:
    python scripts/quality_report.py > quality-report.md
    python scripts/quality_report.py --output quality-report.md
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileMetrics:
    """Metrics for a single file."""

    path: str
    coverage: float | None = None
    coverage_baseline: float | None = None
    complexity_grade: str | None = None  # A, B, C, D, E, F
    max_complexity: int | None = None
    long_functions: list[tuple[str, int]] | None = None  # (name, lines)


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def get_coverage_data() -> dict[str, float]:
    """Get per-file coverage from coverage.py."""
    _, stdout, _ = run_command(["python", "-m", "coverage", "json", "-o", "-"])
    try:
        data = json.loads(stdout)
        return {
            path: round(info["summary"]["percent_covered"], 1)
            for path, info in data.get("files", {}).items()
        }
    except (json.JSONDecodeError, KeyError):
        return {}


def get_coverage_baseline() -> dict[str, float]:
    """Load coverage baseline."""
    baseline_file = Path(".coverage-baseline.json")
    if baseline_file.exists():
        data = json.loads(baseline_file.read_text())
        return {
            path: info["min_coverage"] for path, info in data.get("files", {}).items()
        }
    return {}


def get_complexity_data() -> dict[str, tuple[str, int]]:
    """Get complexity grades and max CC per file using radon."""
    _, stdout, _ = run_command(["python", "-m", "radon", "cc", "src/", "-j"])
    try:
        data = json.loads(stdout)
        result = {}
        for filepath, functions in data.items():
            if not functions:
                continue
            max_cc = max(f["complexity"] for f in functions)
            # Grade based on max complexity
            if max_cc <= 5:
                grade = "A"
            elif max_cc <= 10:
                grade = "B"
            elif max_cc <= 20:
                grade = "C"
            elif max_cc <= 30:
                grade = "D"
            elif max_cc <= 40:
                grade = "E"
            else:
                grade = "F"
            result[filepath] = (grade, max_cc)
        return result
    except (json.JSONDecodeError, KeyError):
        return {}


FUNCTION_LENGTH_WARN = 11
FUNCTION_LENGTH_ERROR = 12


def get_function_length_data() -> dict[str, list[tuple[str, int]]]:
    """Get functions exceeding length thresholds."""
    # Run our function length checker with explicit thresholds
    _, stdout, _ = run_command(
        ["python", "scripts/check_function_length.py", "src/", "--all", "--json",
         "--warn", str(FUNCTION_LENGTH_WARN), "--error", str(FUNCTION_LENGTH_ERROR)]
    )
    try:
        data = json.loads(stdout)
        result = {}
        for item in data.get("violations", []):
            filepath = item["file"]
            if filepath not in result:
                result[filepath] = []
            result[filepath].append((item["function"], item["lines"]))
        return result
    except (json.JSONDecodeError, KeyError):
        return {}


def grade_emoji(grade: str) -> str:
    """Return emoji for complexity grade."""
    return {
        "A": "🟢",
        "B": "🟢",
        "C": "🟡",
        "D": "🟠",
        "E": "🔴",
        "F": "🔴",
    }.get(grade, "⚪")


def coverage_emoji(current: float, baseline: float | None) -> str:
    """Return emoji for coverage status."""
    if baseline is None:
        return "🆕" if current >= 80 else "⚠️"
    if current > baseline:
        return "📈"
    elif current < baseline - 0.5:
        return "📉"
    return "✅"


def generate_report(output_file: str | None = None) -> str:
    """Generate the quality report."""
    coverage = get_coverage_data()
    baseline = get_coverage_baseline()
    complexity = get_complexity_data()
    function_lengths = get_function_length_data()

    # Calculate totals
    total_coverage = (
        sum(coverage.values()) / len(coverage) if coverage else 0
    )
    
    # Count issues
    coverage_drops = sum(
        1 for f, c in coverage.items() 
        if f in baseline and c < baseline[f] - 0.5
    )
    complex_files = sum(1 for _, (g, _) in complexity.items() if g in "DEF")
    long_function_count = sum(len(funcs) for funcs in function_lengths.values())
    
    lines = []
    lines.append("## 📊 Quality Report\n")
    
    # Summary badges
    cov_badge = f"**Coverage:** {total_coverage:.1f}%"
    if coverage_drops > 0:
        cov_badge += f" ({coverage_drops} ⚠️)"
    
    complex_badge = f"**Complexity:** {len(complexity)} files analyzed"
    if complex_files > 0:
        complex_badge += f" ({complex_files} need attention)"
    
    func_badge = ""
    if long_function_count > 0:
        func_badge = f" | **Long functions:** {long_function_count} ⚠️"
    
    lines.append(f"{cov_badge} | {complex_badge}{func_badge}\n")
    
    # Detailed table - only show files needing attention or with changes
    lines.append("<details>")
    lines.append("<summary>📋 Per-file details</summary>\n")
    lines.append("| File | Coverage | Δ | Complexity |")
    lines.append("|------|----------|---|------------|")
    
    all_files = set(coverage.keys()) | set(complexity.keys())
    for filepath in sorted(all_files):
        # Shorten path for display
        short_path = filepath.replace("src/demorec/", "")
        
        # Coverage column
        cov = coverage.get(filepath)
        base = baseline.get(filepath)
        if cov is not None:
            cov_str = f"{cov:.0f}%"
            emoji = coverage_emoji(cov, base)
            delta = ""
            if base is not None:
                diff = cov - base
                if abs(diff) >= 0.5:
                    delta = f"+{diff:.1f}" if diff > 0 else f"{diff:.1f}"
        else:
            cov_str = "-"
            emoji = ""
            delta = ""
        
        # Complexity column
        comp = complexity.get(filepath)
        if comp:
            grade, cc = comp
            comp_str = f"{grade} (CC={cc})"
            comp_str = f"{grade_emoji(grade)} {comp_str}"
        else:
            comp_str = "-"
        
        lines.append(f"| `{short_path}` | {emoji} {cov_str} | {delta} | {comp_str} |")
    
    lines.append("\n</details>\n")
    
    # Action items section - only if there are issues
    action_items = []
    
    # Coverage drops
    for filepath, cov in coverage.items():
        base = baseline.get(filepath)
        if base and cov < base - 0.5:
            short = filepath.replace("src/demorec/", "")
            action_items.append(f"- 📉 `{short}`: coverage dropped {base:.0f}% → {cov:.0f}%")
    
    # High complexity
    for filepath, (grade, cc) in complexity.items():
        if grade in "DEF":
            short = filepath.replace("src/demorec/", "")
            action_items.append(f"- {grade_emoji(grade)} `{short}`: complexity grade {grade} (CC={cc})")
    
    # Long functions
    for filepath, funcs in function_lengths.items():
        short = filepath.replace("src/demorec/", "")
        for func_name, lines_count in funcs[:3]:  # Show top 3 per file
            action_items.append(f"- 📏 `{short}`: `{func_name}()` has {lines_count} lines")
    
    # New files below threshold
    for filepath, cov in coverage.items():
        if filepath not in baseline and cov < 80:
            short = filepath.replace("src/demorec/", "")
            action_items.append(f"- 🆕 `{short}`: new file at {cov:.0f}% (target: 80%)")
    
    if action_items:
        lines.append("### ⚡ Action Items\n")
        lines.extend(action_items)
        lines.append("")
    else:
        lines.append("### ✅ All quality checks passed!\n")
    
    # Legend
    lines.append("<details>")
    lines.append("<summary>ℹ️ Legend</summary>\n")
    lines.append("- 📈 Coverage improved | 📉 Coverage dropped | ✅ Coverage stable | 🆕 New file")
    lines.append("- 🟢 A/B: Low complexity | 🟡 C: Moderate | 🟠 D: High | 🔴 E/F: Very high")
    lines.append("- CC = Cyclomatic Complexity (target: ≤15)")
    lines.append("\n</details>")
    
    report = "\n".join(lines)
    
    if output_file:
        Path(output_file).write_text(report)
        print(f"Report written to {output_file}", file=sys.stderr)
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Generate quality report")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()
    
    report = generate_report(args.output)
    if not args.output:
        print(report)


if __name__ == "__main__":
    main()
