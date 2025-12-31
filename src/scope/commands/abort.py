"""Abort command for scope.

Kills a scope session and removes it.
"""

import click

from scope.core.abort import abort_session_tree
from scope.core.state import get_descendants, load_session


@click.command()
@click.argument("session_id")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt.")
def abort(session_id: str, yes: bool) -> None:
    """Abort a scope session.

    Kills the tmux session and removes it from the list.
    If the session has children, they will also be aborted.

    SESSION_ID is the ID of the session to abort (e.g., "0" or "0.1").

    Examples:

        scope abort 0

        scope abort 0.1

        scope abort 0 -y  # Skip confirmation
    """
    # Check if session exists in state
    session = load_session(session_id)
    if session is None:
        click.echo(f"Error: Session {session_id} not found", err=True)
        raise SystemExit(1)

    # Check for descendants
    descendants = get_descendants(session_id)

    if descendants and not yes:
        # Show confirmation prompt
        child_ids = [s.id for s in descendants]
        click.echo(f"Session {session_id} has {len(descendants)} child session(s):")
        for child_id in child_ids:
            click.echo(f"  - {child_id}")
        click.echo()
        if not click.confirm("Abort all these sessions?"):
            click.echo("Aborted.")
            raise SystemExit(0)

    result = abort_session_tree(session_id)
    for warning in result.warnings:
        click.echo(f"Warning: {warning}", err=True)

    # Abort descendants first (deepest first)
    for descendant in descendants:
        click.echo(f"Aborted child session {descendant.id}")

    # Abort the parent session
    click.echo(f"Aborted session {session_id}")
