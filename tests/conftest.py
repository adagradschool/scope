"""Shared pytest fixtures for scope tests."""

import os
import subprocess

import pytest


@pytest.fixture
def worker_id(request):
    """Get the pytest-xdist worker ID, or 'master' if not running in parallel.

    This fixture provides a consistent way to get worker isolation regardless
    of whether tests are run with -n auto or sequentially.
    """
    # pytest-xdist sets workerinput on the config when running in parallel
    if hasattr(request.config, "workerinput"):
        return request.config.workerinput["workerid"]
    return "master"


def get_worker_socket(worker_id: str) -> str:
    """Get a unique tmux socket name for the given pytest-xdist worker."""
    # worker_id is "master" when not running in parallel, or "gw0", "gw1", etc.
    return f"scope-test-{worker_id}"


def get_worker_session(worker_id: str) -> str:
    """Get a unique tmux session name for the given pytest-xdist worker."""
    return f"scope-test-{worker_id}"


@pytest.fixture
def cleanup_scope_windows(monkeypatch, worker_id):
    """Fixture to cleanup scope tmux windows before and after tests.

    Uses an isolated tmux server (via socket) to avoid affecting development sessions.
    This is critical - without socket isolation, tests can kill the real tmux server.

    Each pytest-xdist worker gets its own tmux socket to enable parallel test execution.
    """
    # Get worker-specific socket and session names for parallel isolation
    test_socket = get_worker_socket(worker_id)
    test_session = get_worker_session(worker_id)

    # Use isolated tmux server via socket - this is the key isolation mechanism
    monkeypatch.setenv("SCOPE_TMUX_SOCKET", test_socket)
    # Use isolated test session name as well
    monkeypatch.setenv("SCOPE_TMUX_SESSION", test_session)

    # Force create_window to use scope-test session by making it think we're not in tmux
    # This ensures windows are created in scope-test, not the current dev session
    monkeypatch.setattr("scope.core.tmux.get_current_session", lambda: None)
    monkeypatch.setattr("scope.core.tmux.in_tmux", lambda: False)
    # Also patch in spawn module since it imports directly
    monkeypatch.setattr("scope.commands.spawn.in_tmux", lambda: False)

    # Use a long-running command instead of 'claude' which may not exist in CI
    # 'cat' blocks forever waiting for input, keeping the window alive for tests
    monkeypatch.setenv("SCOPE_SPAWN_COMMAND", "cat")

    # Skip ready check in tests since we're not using real Claude Code
    monkeypatch.setenv("SCOPE_SKIP_READY_CHECK", "1")

    # Skip loop execution in tests since we're not running real sessions
    monkeypatch.setenv("SCOPE_SKIP_LOOP", "1")

    # Clean before test - kill the isolated test server if it exists
    subprocess.run(
        ["tmux", "-L", test_socket, "kill-server"],
        capture_output=True,
    )
    yield
    # Clean after test - kill the isolated test server
    subprocess.run(
        ["tmux", "-L", test_socket, "kill-server"],
        capture_output=True,
    )


@pytest.fixture
def mock_scope_base(tmp_path, monkeypatch):
    """Mock get_global_scope_base to return tmp_path for test isolation.

    This ensures tests don't write to the real ~/.scope/ directory.
    We need to mock in multiple places because the function is imported
    directly in some modules.

    Also clears SCOPE_SESSION_ID to prevent parent session pollution.
    """

    def mock_fn():
        return tmp_path

    # Clear session ID to prevent test pollution from parent environment
    monkeypatch.delenv("SCOPE_SESSION_ID", raising=False)

    # Mock in the source module
    monkeypatch.setattr("scope.core.state.get_global_scope_base", mock_fn)

    # Mock in modules that import it directly
    monkeypatch.setattr("scope.hooks.handler.get_global_scope_base", mock_fn)
    monkeypatch.setattr("scope.tui.app.get_global_scope_base", mock_fn)

    return tmp_path
