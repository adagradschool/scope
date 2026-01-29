"""Check-termination command for scope.

Evaluates termination criteria for a session and outputs a recommendation.
Designed for orchestrators to call after each iteration to decide whether
to continue looping.
"""

import click
import orjson

from scope.core.state import ensure_scope_dir, resolve_id
from scope.core.termination import (
    evaluate_termination,
    load_iteration_count,
    load_max_iterations,
    load_termination_criteria,
    save_iteration_count,
)


@click.command("check-termination")
@click.argument("session_id")
@click.option(
    "--increment",
    is_flag=True,
    help="Increment the iteration counter before checking",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON instead of human-readable summary",
)
def check_termination(session_id: str, increment: bool, output_json: bool) -> None:
    """Check termination criteria for a session.

    Runs all termination criteria and outputs a recommendation:
    terminate or iterate. The orchestrator retains authority to override.

    Exit codes: 0 = recommend terminate, 1 = error, 2 = recommend iterate.

    Examples:

        scope check-termination 0

        scope check-termination --increment 0

        scope check-termination --json 0
    """
    resolved = resolve_id(session_id)
    if resolved is None:
        click.echo(f"Session {session_id} not found", err=True)
        raise SystemExit(1)

    scope_dir = ensure_scope_dir()
    session_dir = scope_dir / "sessions" / resolved

    criteria = load_termination_criteria(session_dir)
    if criteria is None:
        click.echo(
            f"No termination criteria set for session {session_id}\n"
            f"  Fix: Spawn with --terminate-when to set criteria:\n"
            f'    scope spawn --terminate-when "pytest tests/" "your prompt"',
            err=True,
        )
        raise SystemExit(1)

    # Optionally increment iteration counter
    if increment:
        current = load_iteration_count(session_dir)
        save_iteration_count(session_dir, current + 1)

    iteration = load_iteration_count(session_dir)
    max_iter = load_max_iterations(session_dir)

    result = evaluate_termination(
        criteria=criteria,
        iteration=iteration,
        max_iterations=max_iter,
    )

    if output_json:
        data = {
            "session": resolved,
            "iteration": result.iteration,
            "max_iterations": result.max_iterations,
            "recommend_terminate": result.recommend_terminate,
            "reason": result.reason,
            "checks": [
                {
                    "criterion": c.criterion,
                    "passed": c.passed,
                    "detail": c.detail,
                }
                for c in result.checks
            ],
        }
        click.echo(orjson.dumps(data).decode())
    else:
        click.echo(result.summary())

    # Exit code signals recommendation: 0=terminate, 2=iterate
    if result.recommend_terminate:
        raise SystemExit(0)
    else:
        raise SystemExit(2)
