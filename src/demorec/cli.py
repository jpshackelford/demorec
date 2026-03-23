"""Command-line interface for demorec."""

import subprocess
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .parser import Plan, parse_script
from .preview import TerminalPreviewer
from .runner import Runner
from .stage import (
    calculate_stage_directions,
    detect_checkpoints,
    format_checkpoints_json,
    format_checkpoints_text,
    format_directions_demorec,
    format_directions_json,
    format_directions_text,
    parse_highlights,
)

console = Console()

# Voice configuration data
EDGE_VOICES = {
    "jenny": "Female, US",
    "guy": "Male, US",
    "aria": "Female, US",
    "davis": "Male, US",
    "emma": "Female, US",
    "brian": "Male, US",
    "sonia": "Female, UK",
    "ryan": "Male, UK",
    "natasha": "Female, AU",
    "william": "Male, AU",
}
ELEVEN_VOICES = ["rachel", "adam", "josh", "bella", "sam"]


def _print_plan_summary(plan: Plan):
    """Print summary of parsed plan."""
    console.print(f"[dim]Output:[/] {plan.output}")
    console.print(f"[dim]Segments:[/] {len(plan.segments)}")
    for i, seg in enumerate(plan.segments):
        console.print(f"  [cyan]{i + 1}.[/] {seg.mode} ({len(seg.commands)} commands)")


def _run_recording(plan: Plan):
    """Execute the recording and handle errors."""
    runner = Runner(plan)
    try:
        runner.run()
        console.print(f"\n[bold green]✓[/] Saved to {plan.output}")
    except Exception as e:
        console.print(f"[bold red]Recording error:[/] {e}")
        raise SystemExit(1)


@click.group()
@click.version_option(version=__version__, prog_name="demorec")
def main():
    """Record CLI and web-based demos from a single script."""
    pass


@main.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o", "--output", type=click.Path(path_type=Path), help="Output file (overrides script)"
)
@click.option("--voice", help="TTS voice to use (overrides script)")
@click.option("--dry-run", is_flag=True, help="Parse and plan without recording")
def record(script: Path, output: Path | None, voice: str | None, dry_run: bool):
    """Record a demo from a .demorec script."""
    console.print(f"[bold blue]demorec[/] v{__version__}")
    console.print(f"[dim]Recording:[/] {script}")

    plan = _parse_and_configure(script, output, voice)
    _print_plan_summary(plan)

    if not dry_run:
        _run_recording(plan)
    else:
        console.print("\n[yellow]Dry run - not recording[/]")


def _parse_and_configure(script: Path, output: Path | None, voice: str | None) -> Plan:
    """Parse script and apply overrides."""
    try:
        plan = parse_script(script)
    except Exception as e:
        console.print(f"[bold red]Parse error:[/] {e}")
        raise SystemExit(1)

    if output:
        plan.output = output
    if voice:
        plan.voice = voice
    return plan


@main.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
def validate(script: Path):
    """Validate a .demorec script without recording."""
    console.print("[bold blue]demorec[/] validate")
    console.print(f"[dim]Checking:[/] {script}")

    try:
        plan = parse_script(script)
        console.print("[bold green]✓[/] Valid script")
        console.print(f"  [dim]Output:[/] {plan.output}")
        console.print(f"  [dim]Segments:[/] {len(plan.segments)}")
        console.print(f"  [dim]Total commands:[/] {sum(len(s.commands) for s in plan.segments)}")
    except Exception as e:
        console.print(f"[bold red]✗[/] Invalid: {e}")
        raise SystemExit(1)


@main.command()
def voices():
    """List available TTS voices."""
    console.print("[bold blue]demorec[/] voices\n")
    console.print("[bold green]Microsoft Edge TTS[/] (free, high quality - recommended)")
    for name, desc in EDGE_VOICES.items():
        console.print(f"  edge:{name:12} [dim]{desc}[/]")
    console.print("\n[bold yellow]ElevenLabs[/] (requires paid API subscription)")
    for v in ELEVEN_VOICES:
        console.print(f"  eleven:{v}")


@main.command()
def install():
    """Install browser dependencies (Playwright)."""
    console.print("[bold blue]demorec[/] install")
    console.print("Installing Playwright browsers...")
    result = subprocess.run(["playwright", "install", "chromium"], capture_output=True, text=True)
    if result.returncode == 0:
        console.print("[bold green]✓[/] Browsers installed")
    else:
        console.print("[bold red]✗[/] Installation failed")
        console.print(result.stderr)
        raise SystemExit(1)


@main.command()
@click.option("--rows", "-r", type=int, required=True, help="Terminal rows")
@click.option(
    "--highlights",
    "-h",
    type=str,
    required=True,
    help="Line ranges to highlight (e.g., '6-7,11-16,26-34')",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json", "demorec"]),
    default="text",
    help="Output format",
)
def stage(rows: int, highlights: str, output_format: str):
    """Calculate vim stage directions for highlighting code blocks."""
    blocks = _parse_blocks(highlights)
    directions = calculate_stage_directions(rows, blocks)
    _output_directions(directions, rows, output_format)


def _parse_blocks(highlights: str) -> list:
    """Parse highlight blocks with error handling."""
    try:
        return parse_highlights(highlights)
    except ValueError as e:
        console.print(f"[bold red]Error parsing highlights:[/] {e}")
        console.print("Expected format: '6-7,11-16,26-34' (comma-separated line ranges)")
        raise SystemExit(1)


def _output_directions(directions: list, rows: int, output_format: str):
    """Output directions in the specified format."""
    formatters = {
        "json": lambda: format_directions_json(directions, rows),
        "demorec": lambda: format_directions_demorec(directions),
    }
    print(formatters.get(output_format, lambda: format_directions_text(directions, rows))())


@main.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def checkpoints(script: Path, output_format: str):
    """Detect natural checkpoint locations in a script.

    Automatically identifies "show moments" where verification is useful:

    \b
    - Visual selections (V...G patterns) - highlighted code should be visible
    - Narration points (@narrate:after) - narrated content should be on screen
    - File opens (vim + Enter) - file should be loaded

    Examples:

        demorec checkpoints examples/vim_demo.demorec

        demorec checkpoints script.demorec --format json
    """
    console.print("[bold blue]demorec[/] checkpoints")
    console.print(f"[dim]Analyzing:[/] {script}\n")

    detected = detect_checkpoints(script)

    if output_format == "json":
        print(format_checkpoints_json(detected))
    else:
        print(format_checkpoints_text(detected))


@main.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option("--rows", "-r", type=int, default=30, help="Terminal rows (default: 30)")
@click.option(
    "--screenshots/--no-screenshots",
    default=None,
    help="Always/never capture screenshots (default: on error only)",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    help="Directory for screenshots (default: .demorec_preview)",
)
def preview(script: Path, rows: int, screenshots: bool | None, output_dir: Path | None):
    """Preview a script and verify checkpoints.

    Runs through the script, automatically detecting "show moments" and
    verifying that expected content is visible at each checkpoint.

    \b
    Screenshot behavior:
      (default)        Screenshots only on errors
      --screenshots    Always capture screenshots
      --no-screenshots Never capture screenshots

    Examples:

        demorec preview script.demorec --rows 30

        demorec preview script.demorec --screenshots

        demorec preview script.demorec --no-screenshots
    """
    console.print("[bold blue]demorec[/] preview")
    console.print(f"[dim]Script:[/] {script}")
    console.print(f"[dim]Terminal:[/] {rows} rows")

    segment = _get_terminal_segment(script)
    screenshot_mode = _get_screenshot_mode(screenshots)

    console.print(f"[dim]Screenshots:[/] {screenshot_mode}")
    console.print()

    result = _run_preview(script, segment, rows, screenshot_mode, output_dir)
    _print_preview_results(result)


def _get_terminal_segment(script: Path):
    """Parse script and return first terminal segment."""
    try:
        plan = parse_script(script)
    except Exception as e:
        console.print(f"[bold red]Parse error:[/] {e}")
        raise SystemExit(1)

    terminal_segments = [s for s in plan.segments if s.mode == "terminal" and s.commands]
    if not terminal_segments:
        console.print("[bold red]Error:[/] No terminal segments with commands found in script")
        raise SystemExit(1)

    return terminal_segments[0]


def _get_screenshot_mode(screenshots: bool | None) -> str:
    """Convert screenshots flag to mode string."""
    if screenshots is True:
        return "always"
    elif screenshots is False:
        return "never"
    return "on_error"


def _run_preview(script, segment, rows, screenshot_mode, output_dir):
    """Run preview with progress spinner."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    previewer = TerminalPreviewer(rows=rows, screenshots=screenshot_mode)
    cols = [SpinnerColumn(), TextColumn("[progress.description]{task.description}")]
    with Progress(*cols, console=console) as p:
        p.add_task("Running preview...", total=None)
        return _execute_preview(previewer, script, segment, output_dir)


def _execute_preview(previewer, script, segment, output_dir):
    """Execute preview with error handling."""
    try:
        return previewer.preview(script, segment, output_dir)
    except Exception as e:
        console.print(f"[bold red]Preview error:[/] {e}")
        raise SystemExit(1)


def _print_preview_results(result):
    """Print preview results and exit if failures."""
    console.print()

    for i, r in enumerate(result.results, 1):
        _print_checkpoint_result(i, r)

    if result.failed > 0:
        msg = f"[bold red]Summary: {result.passed}/{result.total} passed, {result.failed} failed[/]"
        console.print(msg)
        if result.screenshot_dir:
            console.print(f"[dim]Screenshots saved to: {result.screenshot_dir}[/]")
        raise SystemExit(1)
    else:
        console.print(f"[bold green]Summary: {result.passed}/{result.total} passed[/]")


def _print_checkpoint_result(i: int, r):
    """Print a single checkpoint result."""
    status = "[bold green]✓[/]" if r.passed else "[bold red]✗[/]"
    console.print(f"{status} Checkpoint {i} (line {r.checkpoint.line_number}): ", end="")
    console.print("[green]PASS[/]" if r.passed else "[red]FAIL[/]")

    if r.expected_lines:
        console.print(f"    Expected: lines {r.expected_lines[0]}-{r.expected_lines[1]}")
    if r.visible_lines:
        console.print(f"    Visible:  lines {r.visible_lines[0]}-{r.visible_lines[1]}")
    if r.error_message:
        console.print(f"    [red]Error: {r.error_message}[/]")
    if r.screenshot_path:
        console.print(f"    Screenshot: {r.screenshot_path}")
    console.print()


if __name__ == "__main__":
    main()
