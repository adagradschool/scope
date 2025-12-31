"""Poll command for scope.

Returns session status as JSON.
"""

import click
import orjson

from scope.core.state import ensure_scope_dir, load_session, resolve_id


@click.command()
@click.argument("session_id")
def poll(session_id: str) -> None:
    """Poll a session's status.

    Returns JSON with current status and activity.

    SESSION_ID is the ID or alias of the session to poll.

    Examples:

        scope poll 0

        scope poll 0.1

        scope poll my-task
    """
    # Resolve alias to session ID if needed
    resolved_id = resolve_id(session_id)
    if resolved_id is None:
        click.echo(f"Session {session_id} not found", err=True)
        raise SystemExit(1)

    session = load_session(resolved_id)
    if session is None:
        click.echo(f"Session {session_id} not found", err=True)
        raise SystemExit(1)

    # Use resolved ID for file lookups
    session_id = resolved_id

    result: dict[str, str] = {"status": session.state}

    scope_dir = ensure_scope_dir()
    session_dir = scope_dir / "sessions" / session_id

    # Activity will be added in Slice 7
    activity_file = session_dir / "activity"
    if activity_file.exists():
        activity = ""
        for line in activity_file.read_text().splitlines():
            if line.strip():
                activity = line.strip()
        if activity:
            if session.state in {"done", "aborted", "exited"}:
                activity = past_tense_activity(activity)
            result["activity"] = activity

    # Include result if session is done
    result_file = session_dir / "result"
    if result_file.exists():
        result["result"] = result_file.read_text()

    click.echo(orjson.dumps(result).decode())


def past_tense_activity(activity: str) -> str:
    """Convert present-tense activity to past tense for done sessions."""
    conversions = {
        "reading ": "read ",
        "editing ": "edited ",
        "running: ": "ran: ",
        "searching: ": "searched: ",
        "spawning subtask": "spawned subtask",
        "finding: ": "found: ",
        "reading file": "read file",
        "editing file": "edited file",
        "running command": "ran command",
        "searching": "searched",
        "finding files": "found files",
    }
    for prefix, replacement in conversions.items():
        if activity.startswith(prefix):
            return replacement + activity[len(prefix) :]
    return activity
