"""Optimize command for scope.

Runs DSPy optimization on skill routing using training data from session trajectories.
"""

from pathlib import Path

import click
import dspy
import orjson

from scope.core.state import ensure_scope_dir
from scope.prompts.dspy_skills.optimize import SkillOptimizer, TrainingDataCollector


@click.command()
@click.option(
    "--strategy",
    type=click.Choice(["bootstrap", "mipro"]),
    default="bootstrap",
    help="Optimization strategy (bootstrap=BootstrapFewShot, mipro=MIPROv2)",
)
@click.option(
    "--min-examples",
    type=int,
    default=10,
    help="Minimum number of training examples required",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path for optimized router JSON (default: scope_dir/optimized_router.json)",
)
@click.option(
    "--export-markdown",
    is_flag=True,
    help="Export optimized prompts to markdown files",
)
@click.option(
    "--model",
    default="anthropic/claude-sonnet-4-20250514",
    help="Model to use for optimization",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show stats without running optimization",
)
def optimize(
    strategy: str,
    min_examples: int,
    output: Path | None,
    export_markdown: bool,
    model: str,
    dry_run: bool,
) -> None:
    """Optimize skill routing using DSPy.

    Collects training data from completed scope sessions and runs
    optimization to improve skill routing accuracy.

    Examples:

        scope optimize --dry-run

        scope optimize --strategy bootstrap --min-examples 20

        scope optimize --export-markdown -o custom_router.json
    """
    scope_dir = ensure_scope_dir()

    # Collect training data
    click.echo("Collecting training data from session trajectories...")
    collector = TrainingDataCollector()
    dataset = collector.collect(min_examples=min_examples)

    # Show stats
    click.echo("\nTraining Data Statistics:")
    click.echo(f"  Total sessions scanned: {dataset.metadata.get('total_sessions_scanned', 0)}")
    click.echo(f"  Total invocations: {dataset.metadata.get('total_invocations', 0)}")
    click.echo(f"  Successful invocations: {dataset.metadata.get('successful_invocations', 0)}")
    click.echo(f"  Failed invocations: {dataset.metadata.get('failed_invocations', 0)}")
    click.echo(f"  Training examples: {len(dataset)}")

    skill_dist = dataset.metadata.get("skill_distribution", {})
    if skill_dist:
        click.echo("\n  Skill distribution:")
        for skill, count in sorted(skill_dist.items()):
            click.echo(f"    {skill}: {count}")

    if warning := dataset.metadata.get("warning"):
        click.echo(f"\nWarning: {warning}", err=True)

    if dry_run:
        click.echo("\nDry run complete. No optimization performed.")
        return

    if len(dataset) < min_examples:
        click.echo(
            f"\nError: Not enough training examples ({len(dataset)} < {min_examples})\n"
            f"  Cause: Insufficient skill invocations in completed sessions.\n"
            f"  Fix: Use more skills in your sessions, or lower --min-examples.",
            err=True,
        )
        raise SystemExit(1)

    # Configure DSPy
    click.echo(f"\nConfiguring DSPy with model: {model}")
    dspy.configure(lm=dspy.LM(model))

    # Run optimization
    click.echo(f"\nRunning {strategy} optimization...")
    optimizer = SkillOptimizer()
    optimized_router = optimizer.optimize(dataset, strategy=strategy)

    # Determine output path
    if output is None:
        output = scope_dir / "optimized_router.json"

    # Save optimized router
    optimizer.save(optimized_router, output)
    click.echo(f"\nOptimized router saved to: {output}")

    # Export markdown if requested
    if export_markdown:
        markdown_dir = scope_dir / "optimized_prompts"
        markdown_dir.mkdir(parents=True, exist_ok=True)
        markdown_outputs = optimizer.export_to_markdown(optimized_router, markdown_dir)

        if markdown_outputs:
            click.echo(f"\nExported {len(markdown_outputs)} optimized prompts to: {markdown_dir}")
            for skill_name in markdown_outputs:
                click.echo(f"  - {skill_name}_optimized.md")
        else:
            click.echo("\nNo prompts to export (no demos in optimized router).")

    click.echo("\nOptimization complete!")
