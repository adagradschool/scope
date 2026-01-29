"""Poll command for scope.

Returns lightweight session status as JSON — designed for non-blocking check-ins
that don't bloat orchestrator context.
"""

import click
import orjson

from scope.core.state import (
    ensure_scope_dir,
    load_all,
    load_session,
    load_trajectory_index,
    resolve_id,
)


@click.command()
@click.argument("session_ids", nargs=-1, required=False)
@click.option("--all", "poll_all", is_flag=True, help="Poll all active sessions")
@click.option("--trajectory", is_flag=True, help="Include trajectory index in output")
def poll(session_ids: tuple[str, ...], poll_all: bool, trajectory: bool) -> None:
    """Poll session status (lightweight check-in).

    Returns concise JSON with status, elapsed time, tool call count,
    and last activity. Designed to not bloat orchestrator context.
    Use 'scope wait' to get full results.

    SESSION_IDS are the IDs or aliases of sessions to poll.

    Examples:

        scope poll 0

        scope poll 0 1 2

        scope poll --all
    """
    if poll_all:
        sessions = load_all()
        if not sessions:
            click.echo("No sessions found", err=True)
            raise SystemExit(1)
        for session in sessions:
            click.echo(orjson.dumps(_build_status(session.id, trajectory)).decode())
        return

    if not session_ids:
        click.echo("Error: provide session IDs or use --all", err=True)
        raise SystemExit(1)

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

        click.echo(orjson.dumps(_build_status(resolved_id, trajectory)).decode())


def _build_status(session_id: str, include_trajectory: bool = False) -> dict:
    """Build a compact status dict for a session.

    Includes: id, status, elapsed, tool_calls, activity.
    Excludes full result text (use 'scope wait' for that).
    """
    from datetime import datetime, timezone

    session = load_session(session_id)
    if session is None:
        return {"id": session_id, "status": "not_found"}

    result: dict[str, object] = {"id": session_id, "status": session.state}

    # Elapsed time since creation
    now = datetime.now(timezone.utc)
    created = session.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    elapsed_seconds = int((now - created).total_seconds())
    result["elapsed"] = _format_elapsed(elapsed_seconds)

    # Tool call count from trajectory index
    scope_dir = ensure_scope_dir()
    session_dir = scope_dir / "sessions" / session_id

    traj_index = load_trajectory_index(session_id)
    if traj_index is not None:
        tool_calls = traj_index.get("tool_calls", [])
        result["tool_calls"] = len(tool_calls)
    else:
        result["tool_calls"] = 0

    # Activity (last line of activity file)
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

    # Include full trajectory index only if requested
    if include_trajectory and traj_index is not None:
        result["trajectory_index"] = traj_index

    return result


def _format_elapsed(seconds: int) -> str:
    """Format elapsed seconds as human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m{seconds % 60}s"
    hours = minutes // 60
    return f"{hours}h{minutes % 60}m"


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
