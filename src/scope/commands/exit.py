"""Exit command for scope.

Allows a session to cleanly exit with a reason.
"""

import os

import click

from scope.core.state import save_exit_reason, update_state


@click.command("exit")
@click.argument("reason")
def exit_cmd(reason: str) -> None:
    """Exit the current scope session with a reason.

    REASON is an explanation of why the session is exiting.

    This sets the session state to "exited" and saves the reason.
    The session ID is read from the SCOPE_SESSION_ID environment variable.

    Examples:

        scope exit "Auth module needs event-driven redesign"
    """
    session_id = os.environ.get("SCOPE_SESSION_ID")
    if not session_id:
        click.echo("Error: SCOPE_SESSION_ID not set", err=True)
        raise SystemExit(1)

    try:
        update_state(session_id, "exited")
        save_exit_reason(session_id, reason)
    except FileNotFoundError:
        click.echo(f"Error: Session {session_id} not found", err=True)
        raise SystemExit(1)

    click.echo(f"Session {session_id} exited: {reason}")
