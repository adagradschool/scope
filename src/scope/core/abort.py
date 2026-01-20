"""Shared abort helpers for scope sessions."""

from dataclasses import dataclass

from scope.core.state import delete_session, get_descendants
from scope.core.tmux import (
    TmuxError,
    get_current_session,
    get_scope_session,
    has_session,
    has_window_in_session,
    kill_session,
    kill_window_in_session,
    terminate_pane_processes,
    tmux_session_name,
    tmux_window_name,
)


@dataclass
class AbortResult:
    """Outcome of aborting a session tree."""

    aborted_ids: list[str]
    warnings: list[str]


def abort_session_tree(session_id: str) -> AbortResult:
    """Abort a session and all descendants.

    Args:
        session_id: The root session ID to abort.

    Returns:
        AbortResult with ordered aborted IDs and warning messages.
    """
    session_ids = session_tree_ids(session_id)
    window_names = [tmux_window_name(sid) for sid in session_ids]

    sessions_to_check = [get_scope_session()]
    current = get_current_session()
    if current and current not in sessions_to_check:
        sessions_to_check.append(current)

    warnings: list[str] = []

    for sid in session_ids:
        tmux_name = tmux_session_name(sid)
        if has_session(tmux_name):
            terminate_pane_processes(tmux_name)
            try:
                kill_session(tmux_name)
            except TmuxError as e:
                warnings.append(str(e))

    for window_name in window_names:
        for tmux_session in sessions_to_check:
            if has_window_in_session(tmux_session, window_name):
                terminate_pane_processes(f"{tmux_session}:{window_name}")
                try:
                    kill_window_in_session(tmux_session, window_name)
                except TmuxError as e:
                    warnings.append(str(e))

    for sid in session_ids:
        try:
            delete_session(sid)
        except FileNotFoundError:
            pass  # Already gone

    return AbortResult(aborted_ids=session_ids, warnings=warnings)


def session_tree_ids(session_id: str) -> list[str]:
    """Return descendant IDs (deepest-first) plus the root session ID."""
    descendants = get_descendants(session_id)
    return [s.id for s in descendants] + [session_id]
