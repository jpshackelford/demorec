"""Command-line interface for demorec."""

import click
from pathlib import Path
from rich.console import Console

from . import __version__
from .parser import parse_script
from .runner import Runner
from .stage import (
    parse_highlights,
    calculate_stage_directions,
    format_directions_text,
    format_directions_json,
    format_directions_demorec,
    detect_checkpoints,
    format_checkpoints_text,
    format_checkpoints_json,
)

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="demorec")
def main():
    """Record CLI and web-based demos from a single script."""
    pass


@main.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file (overrides script)")
@click.option("--voice", help="TTS voice to use (overrides script)")
@click.option("--dry-run", is_flag=True, help="Parse and plan without recording")
def record(script: Path, output: Path | None, voice: str | None, dry_run: bool):
    """Record a demo from a .demorec script."""
    console.print(f"[bold blue]demorec[/] v{__version__}")
    console.print(f"[dim]Recording:[/] {script}")
    
    # Parse the script
    try:
        plan = parse_script(script)
    except Exception as e:
        console.print(f"[bold red]Parse error:[/] {e}")
        raise SystemExit(1)
    
    # Override settings from CLI
    if output:
        plan.output = output
    if voice:
        plan.voice = voice
    
    console.print(f"[dim]Output:[/] {plan.output}")
    console.print(f"[dim]Segments:[/] {len(plan.segments)}")
    
    for i, seg in enumerate(plan.segments):
        console.print(f"  [cyan]{i+1}.[/] {seg.mode} ({len(seg.commands)} commands)")
    
    if dry_run:
        console.print("\n[yellow]Dry run - not recording[/]")
        return
    
    # Run the recording
    runner = Runner(plan)
    try:
        runner.run()
        console.print(f"\n[bold green]✓[/] Saved to {plan.output}")
    except Exception as e:
        console.print(f"[bold red]Recording error:[/] {e}")
        raise SystemExit(1)


@main.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
def validate(script: Path):
    """Validate a .demorec script without recording."""
    console.print(f"[bold blue]demorec[/] validate")
    console.print(f"[dim]Checking:[/] {script}")
    
    try:
        plan = parse_script(script)
        console.print(f"[bold green]✓[/] Valid script")
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
    edge_voices = {
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
    for name, desc in edge_voices.items():
        console.print(f"  edge:{name:12} [dim]{desc}[/]")
    
    console.print("\n[bold yellow]ElevenLabs[/] (requires paid API subscription)")
    eleven_voices = ["rachel", "adam", "josh", "bella", "sam"]
    for v in eleven_voices:
        console.print(f"  eleven:{v}")


@main.command()
def install():
    """Install browser dependencies (Playwright)."""
    import subprocess
    console.print("[bold blue]demorec[/] install")
    console.print("Installing Playwright browsers...")
    
    result = subprocess.run(
        ["playwright", "install", "chromium"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        console.print("[bold green]✓[/] Browsers installed")
    else:
        console.print(f"[bold red]✗[/] Installation failed")
        console.print(result.stderr)
        raise SystemExit(1)


@main.command()
@click.option("--rows", "-r", type=int, required=True, help="Terminal rows")
@click.option("--highlights", "-h", type=str, required=True, 
              help="Line ranges to highlight (e.g., '6-7,11-16,26-34')")
@click.option("--format", "-f", "output_format", type=click.Choice(["text", "json", "demorec"]), 
              default="text", help="Output format")
def stage(rows: int, highlights: str, output_format: str):
    """Calculate vim stage directions for highlighting code blocks.
    
    Given terminal dimensions and line ranges to highlight, outputs
    the optimal vim commands for scrolling and selecting each block.
    
    Examples:
    
        demorec stage --rows 30 --highlights "6-7,11-16,26-34,63-73"
        
        demorec stage -r 30 -h "10-20,45-60" --format json
        
        demorec stage -r 30 -h "1-10,50-60" --format demorec
    """
    try:
        blocks = parse_highlights(highlights)
    except ValueError as e:
        console.print(f"[bold red]Error parsing highlights:[/] {e}")
        console.print("Expected format: '6-7,11-16,26-34' (comma-separated line ranges)")
        raise SystemExit(1)
    
    directions = calculate_stage_directions(rows, blocks)
    
    if output_format == "json":
        print(format_directions_json(directions, rows))
    elif output_format == "demorec":
        print(format_directions_demorec(directions))
    else:
        print(format_directions_text(directions, rows))


@main.command()
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "-f", "output_format", type=click.Choice(["text", "json"]), 
              default="text", help="Output format")
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
    console.print(f"[bold blue]demorec[/] checkpoints")
    console.print(f"[dim]Analyzing:[/] {script}\n")
    
    detected = detect_checkpoints(script)
    
    if output_format == "json":
        print(format_checkpoints_json(detected))
    else:
        print(format_checkpoints_text(detected))


if __name__ == "__main__":
    main()
