"""Wait command for scope.

Blocks until session(s) complete (done or aborted).
"""

from pathlib import Path

import click
from watchfiles import watch

from scope.core.state import (
    ensure_scope_dir,
    get_failed_reason,
    load_session,
    resolve_id,
)


TERMINAL_STATES = {"done", "aborted", "failed", "exited"}


@click.command()
@click.argument("session_ids", nargs=-1, required=True)
def wait(session_ids: tuple[str, ...]) -> None:
    """Wait for session(s) to complete.

    Blocks until all sessions reach a terminal state (done, aborted, or failed).
    Outputs result file content (if any). Exit code indicates status:
    0 = all done, 1 = error, 2 = any aborted, 3 = any failed.

    SESSION_IDS are the IDs or aliases of sessions to wait for.

    Examples:

        scope wait 0

        scope wait 0 1 2

        scope wait my-task
    """
    scope_dir = ensure_scope_dir()

    # Resolve aliases to session IDs
    resolved_ids: list[str] = []
    for session_id in session_ids:
        resolved = resolve_id(session_id)
        if resolved is None:
            click.echo(f"Session {session_id} not found", err=True)
            raise SystemExit(1)
        resolved_ids.append(resolved)

    # Use resolved IDs from here on
    session_ids = tuple(resolved_ids)

    # Validate all sessions exist
    pending: dict[str, Path] = {}  # session_id -> session_dir
    for session_id in session_ids:
        session = load_session(session_id)
        if session is None:
            click.echo(f"Session {session_id} not found", err=True)
            raise SystemExit(1)
        pending[session_id] = scope_dir / "sessions" / session_id

    results: dict[str, str] = {}  # session_id -> state

    # Check for already-completed sessions
    for session_id in list(pending.keys()):
        session = load_session(session_id)
        if session and session.state in TERMINAL_STATES:
            results[session_id] = session.state
            del pending[session_id]

    # If all already done, output and exit
    if not pending:
        _output_results(session_ids, results)
        return

    # Watch all pending session directories
    watch_paths = list(pending.values())

    for changes in watch(*watch_paths):
        for _, path in changes:
            path = Path(path)
            # Check if this is a state file change
            if path.name == "state":
                session_id = path.parent.name
                if session_id in pending:
                    session = load_session(session_id)
                    if session is None:
                        click.echo(f"Session {session_id} was deleted", err=True)
                        raise SystemExit(1)
                    if session.state in TERMINAL_STATES:
                        results[session_id] = session.state
                        del pending[session_id]

        # All done?
        if not pending:
            _output_results(session_ids, results)
            return


def _format_header(session_id: str) -> str:
    """Format session header with alias if available.

    Returns:
        "[alias (id)]" if session has alias, otherwise "[id]"
    """
    session = load_session(session_id)
    if session and session.alias:
        return f"[{session.alias} ({session_id})]"
    return f"[{session_id}]"


def _output_results(session_ids: tuple[str, ...], states: dict[str, str]) -> None:
    """Output results for all sessions and exit with appropriate code."""
    scope_dir = ensure_scope_dir()
    any_aborted = False
    any_failed = False
    multiple = len(session_ids) > 1

    for session_id in session_ids:
        state = states.get(session_id)

        if state == "failed":
            any_failed = True
            # Output failure reason if available
            reason = get_failed_reason(session_id)
            if reason:
                if multiple:
                    click.echo(_format_header(session_id))
                click.echo(f"Failed: {reason}", nl=False)
                if multiple:
                    click.echo("\n")
            continue

        result_file = scope_dir / "sessions" / session_id / "result"
        if result_file.exists():
            if multiple:
                click.echo(_format_header(session_id))
            click.echo(result_file.read_text(), nl=False)
            if multiple:
                click.echo("\n")

        if state in {"aborted", "exited"}:
            any_aborted = True

    # Failed takes priority over aborted for exit code
    if any_failed:
        raise SystemExit(3)
    if any_aborted:
        raise SystemExit(2)
