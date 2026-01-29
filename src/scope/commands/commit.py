"""Commit command for scope.

Allows an agent to commit to a pattern (TDD, RALPH, etc.) for its current session.
"""

import os

import click

from scope.core.contract import PATTERN_PHASES
from scope.core.state import (
    advance_pattern_phase,
    load_pattern_state,
    save_pattern_state,
)


@click.command()
@click.argument("pattern")
def commit(pattern: str) -> None:
    """Commit the current session to a pattern.

    Registers a pattern commitment for the current session. Scope will
    re-inject pattern state after each prompt to prevent drift.

    PATTERN is the pattern name (e.g., tdd, ralph, map-reduce).

    Examples:

        scope commit tdd

        scope commit ralph
    """
    session_id = os.environ.get("SCOPE_SESSION_ID", "")
    if not session_id:
        click.echo(
            "Error: not in a scope session (SCOPE_SESSION_ID not set)\n"
            "  Cause: scope commit must be run from within a scope session.\n"
            "  Fix: Use scope spawn to create a session first.",
            err=True,
        )
        raise SystemExit(1)

    pattern_lower = pattern.lower()
    known_patterns = list(PATTERN_PHASES.keys())

    if pattern_lower not in PATTERN_PHASES:
        click.echo(
            f"Error: unknown pattern '{pattern}'\n"
            f"  Known patterns: {', '.join(known_patterns)}\n"
            f"  Fix: Use one of the known patterns:\n"
            f"    scope commit tdd",
            err=True,
        )
        raise SystemExit(1)

    phases = PATTERN_PHASES[pattern_lower]

    try:
        save_pattern_state(
            session_id=session_id,
            pattern=pattern_lower,
            phases=phases,
        )
    except FileNotFoundError:
        click.echo(
            f"Error: session {session_id} not found\n"
            "  Cause: The session directory does not exist.\n"
            "  Fix: Ensure you are in a valid scope session.",
            err=True,
        )
        raise SystemExit(1)

    if phases:
        phases_str = " → ".join(phases)
        click.echo(f"Committed to {pattern_lower} ({phases_str})")
    else:
        click.echo(f"Committed to {pattern_lower}")


@click.command()
def advance() -> None:
    """Advance to the next phase in the committed pattern.

    Marks the current phase as completed and moves to the next one.

    Examples:

        scope advance
    """
    session_id = os.environ.get("SCOPE_SESSION_ID", "")
    if not session_id:
        click.echo(
            "Error: not in a scope session (SCOPE_SESSION_ID not set)\n"
            "  Cause: scope advance must be run from within a scope session.\n"
            "  Fix: Use scope spawn to create a session first.",
            err=True,
        )
        raise SystemExit(1)

    state = load_pattern_state(session_id)
    if state is None:
        click.echo(
            "Error: no pattern committed for this session\n"
            "  Cause: You must commit to a pattern before advancing.\n"
            "  Fix: Commit first:\n"
            "    scope commit tdd",
            err=True,
        )
        raise SystemExit(1)

    updated = advance_pattern_phase(session_id)
    if updated is None:
        click.echo("No more phases to advance to.")
        return

    if updated["current"]:
        click.echo(
            f"Advanced: completed {state['current']}. "
            f"Now in {updated['current']} phase."
        )
    else:
        completed_str = ", ".join(updated["completed"])
        click.echo(f"All phases complete ({completed_str}).")
