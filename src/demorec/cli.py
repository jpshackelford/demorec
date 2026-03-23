"""Command-line interface for demorec."""

import subprocess
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .parser import Plan, parse_script
from .runner import Runner

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

    try:
        plan = parse_script(script)
    except Exception as e:
        console.print(f"[bold red]Parse error:[/] {e}")
        raise SystemExit(1)

    if output:
        plan.output = output
    if voice:
        plan.voice = voice

    _print_plan_summary(plan)

    if dry_run:
        console.print("\n[yellow]Dry run - not recording[/]")
        return

    _run_recording(plan)


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


if __name__ == "__main__":
    main()
