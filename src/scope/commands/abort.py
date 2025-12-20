"""Abort command for scope.

Kills a scope session and removes it.
"""

import click

from scope.core.state import delete_session, load_session
from scope.core.tmux import TmuxError, has_session, kill_session


@click.command()
@click.argument("session_id")
def abort(session_id: str) -> None:
    """Abort a scope session.

    Kills the tmux session and removes it from the list.

    SESSION_ID is the ID of the session to abort (e.g., "0" or "0.1").

    Examples:

        scope abort 0

        scope abort 0.1
    """
    # Check if session exists in state
    session = load_session(session_id)
    if session is None:
        click.echo(f"Error: Session {session_id} not found", err=True)
        raise SystemExit(1)

    # Kill the tmux session if it exists
    tmux_name = f"scope-{session_id}"
    if has_session(tmux_name):
        try:
            kill_session(tmux_name)
        except TmuxError as e:
            click.echo(f"Warning: {e}", err=True)

    # Delete session from filesystem
    try:
        delete_session(session_id)
    except FileNotFoundError:
        pass  # Already gone

    click.echo(f"Aborted session {session_id}")
