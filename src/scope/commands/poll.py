"""Poll command for scope.

Returns session status as JSON.
"""

import click
import orjson

from scope.core.state import (
    ensure_scope_dir,
    has_trajectory,
    load_session,
    load_trajectory_index,
    resolve_id,
)


@click.command()
@click.argument("session_ids", nargs=-1, required=True)
@click.option("--trajectory", is_flag=True, help="Include trajectory index in output")
def poll(session_ids: tuple[str, ...], trajectory: bool) -> None:
    """Poll session status(es).

    Returns JSON with current status and activity.
    For multiple sessions, outputs one JSON object per line.

    SESSION_IDS are the IDs or aliases of sessions to poll.

    Examples:

        scope poll 0

        scope poll 0 1 2

        scope poll my-task other-task
    """
    for session_id in session_ids:
        # Resolve alias to session ID if needed
        resolved_id = resolve_id(session_id)
        if resolved_id is None:
            click.echo(f"Session {session_id} not found", err=True)
            raise SystemExit(1)

        session = load_session(resolved_id)
        if session is None:
            click.echo(f"Session {session_id} not found", err=True)
            raise SystemExit(1)

        result: dict[str, str] = {"id": resolved_id, "status": session.state}

        scope_dir = ensure_scope_dir()
        session_dir = scope_dir / "sessions" / resolved_id

        # Activity will be added in Slice 7
        activity_file = session_dir / "activity"
        if activity_file.exists():
            activity = ""
            for line in activity_file.read_text().splitlines():
                if line.strip():
                    activity = line.strip()
            if activity:
                if session.state in {"done", "aborted", "exited", "evicted"}:
                    activity = past_tense_activity(activity)
                result["activity"] = activity

        # Include result if session is done
        result_file = session_dir / "result"
        if result_file.exists():
            result["result"] = result_file.read_text()

        # Include trajectory index if requested and available
        if trajectory and has_trajectory(resolved_id):
            traj_index = load_trajectory_index(resolved_id)
            if traj_index is not None:
                result["trajectory_index"] = traj_index

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
