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
    load_trajectory_index,
    resolve_id,
)


TERMINAL_STATES = {"done", "aborted", "failed", "exited"}


@click.command()
@click.argument("session_ids", nargs=-1, required=True)
@click.option(
    "--summary", is_flag=True, help="Output compact summary instead of full result"
)
def wait(session_ids: tuple[str, ...], summary: bool) -> None:
    """Wait for session(s) to complete.

    Blocks until all sessions reach a terminal state (done, aborted, or failed).
    Outputs result file content (if any). Exit code indicates status:
    0 = all done, 1 = error, 2 = any aborted, 3 = any failed.

    Use --summary for compact output suitable for orchestrator context protection.

    SESSION_IDS are the IDs or aliases of sessions to wait for.

    Examples:

        scope wait 0

        scope wait --summary 0

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
        _output_results(session_ids, results, summary)
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
            _output_results(session_ids, results, summary)
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


def _output_results(
    session_ids: tuple[str, ...], states: dict[str, str], summary: bool = False
) -> None:
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
                if summary:
                    click.echo(f"FAIL: {reason}", nl=False)
                else:
                    click.echo(f"Failed: {reason}", nl=False)
                if multiple:
                    click.echo("\n")
            elif summary:
                if multiple:
                    click.echo(_format_header(session_id))
                click.echo("FAIL", nl=False)
                if multiple:
                    click.echo("\n")
            continue

        if summary:
            _output_summary(session_id, state, multiple)
        else:
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


def _output_summary(session_id: str, state: str | None, multiple: bool) -> None:
    """Output a natural language summary for a session.

    Uses a claude -p call to summarize what the session accomplished and what
    remains, following the same pattern as summarize_task in hooks/handler.py.
    """
    scope_dir = ensure_scope_dir()
    session_dir = scope_dir / "sessions" / session_id

    if multiple:
        click.echo(_format_header(session_id))

    # Determine pass/fail status
    if state in {"aborted", "exited"}:
        status = "ABORT"
    else:
        status = "PASS"

    # Load session task and result content
    session = load_session(session_id)
    task = session.task if session and session.task else "unknown task"

    result_file = session_dir / "result"
    result_text = result_file.read_text().strip() if result_file.exists() else ""

    # Extract metadata from trajectory index
    files_changed = 0
    tests = "none"
    traj_index = load_trajectory_index(session_id)
    if traj_index is not None:
        tool_summary = traj_index.get("tool_summary", {})
        files_changed = tool_summary.get("Edit", 0) + tool_summary.get("Write", 0)
        if tool_summary.get("Bash", 0) > 0:
            tests = _detect_test_status(session_dir)

    summary = _summarize_result(task, result_text, status)

    parts = [status, summary, f"files_changed={files_changed}", f"tests={tests}"]
    click.echo(" | ".join(parts), nl=False)

    if multiple:
        click.echo("\n")


def _summarize_result(task: str, result_text: str, status: str) -> str:
    """Summarize a session result into a natural language description using Claude CLI.

    Delegates to the shared summarize utility in scope.core.summarize.
    """
    from scope.core.summarize import summarize

    if not result_text:
        if status == "ABORT":
            return f"{task} — aborted before producing a result"
        return task

    return summarize(
        f"Task: {task}\n\nResult:\n{result_text[:2000]}\n\nSummary:",
        goal=(
            "You are a progress summarizer. Given a task and its result, output a 1-2 sentence "
            "summary of what was accomplished and what is left to do. Be specific and concise. "
            "No quotes, no markdown."
        ),
        max_length=300,
        fallback=task,
    )


def _detect_test_status(session_dir: Path) -> str:
    """Detect test pass/fail from result text.

    Scans for common test framework output patterns.
    Returns 'pass', 'fail', or 'none'.
    """
    result_file = session_dir / "result"
    if not result_file.exists():
        return "none"

    text = result_file.read_text().lower()
    # Check for failure indicators first
    fail_indicators = ["failed", "failure", "error", "failing"]
    pass_indicators = ["passed", "passing", "all tests pass", "tests pass", "green"]

    has_fail = any(indicator in text for indicator in fail_indicators)
    has_pass = any(indicator in text for indicator in pass_indicators)

    if has_fail:
        return "fail"
    if has_pass:
        return "pass"
    return "none"
