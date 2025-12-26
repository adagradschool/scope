"""Shared test helpers for scope tests."""

import os


def tmux_cmd(args: list[str]) -> list[str]:
    """Build a tmux command using the test socket if SCOPE_TMUX_SOCKET is set.

    This should be used by all test helpers that call tmux directly.
    The SCOPE_TMUX_SOCKET env var is set by the cleanup_scope_windows fixture
    with a worker-specific value for parallel test isolation.
    """
    socket = os.environ.get("SCOPE_TMUX_SOCKET")
    if socket:
        return ["tmux", "-L", socket] + args
    return ["tmux"] + args
