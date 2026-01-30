"""Tests for abort command."""

import subprocess
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.core.session import Session
from scope.core.state import (
    delete_session,
    get_descendants,
    load_session,
    save_session,
    update_state,
)

from tests.helpers import tmux_cmd


def tmux_available() -> bool:
    """Check if tmux is available."""
    result = subprocess.run(["which", "tmux"], capture_output=True)
    return result.returncode == 0


def session_exists(session_name: str) -> bool:
    """Check if a tmux session exists."""
    result = subprocess.run(
        tmux_cmd(["has-session", "-t", session_name]),
        capture_output=True,
    )
    return result.returncode == 0


@pytest.fixture
def cleanup_scope_sessions(cleanup_scope_windows):
    """Fixture to cleanup scope tmux sessions before and after tests.

    Depends on cleanup_scope_windows to set up socket isolation.
    """
    for i in range(10):
        subprocess.run(tmux_cmd(["kill-session", "-t", f"scope-{i}"]), capture_output=True)
    yield
    for i in range(10):
        subprocess.run(tmux_cmd(["kill-session", "-t", f"scope-{i}"]), capture_output=True)


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_abort_help(runner):
    """Test abort --help shows usage."""
    result = runner.invoke(main, ["abort", "--help"])
    assert result.exit_code == 0
    assert "Abort a scope session" in result.output


def test_abort_session_not_found(runner, mock_scope_base):
    """Test aborting non-existent session shows error."""
    result = runner.invoke(main, ["abort", "999"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_abort_deletes_session(runner, mock_scope_base, cleanup_scope_windows):
    """Test abort deletes the session."""
    # Create a session manually (without tmux)
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["abort", "0"])
    assert result.exit_code == 0
    assert "Aborted session 0" in result.output

    # Verify session was deleted
    assert load_session("0") is None


@pytest.mark.skipif(not tmux_available(), reason="tmux not installed")
def test_abort_kills_tmux_session(runner, mock_scope_base, cleanup_scope_sessions):
    """Test abort kills the tmux session."""
    # Create a real tmux session
    subprocess.run(
        tmux_cmd(["new-session", "-d", "-s", "scope-0", "cat"]),
        capture_output=True,
    )
    assert session_exists("scope-0")

    # Create session state
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["abort", "0"])
    assert result.exit_code == 0

    # Verify tmux session was killed
    assert not session_exists("scope-0")

    # Verify session was deleted
    assert load_session("0") is None


def test_update_state_function(mock_scope_base):
    """Test update_state function."""
    # Create a session
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Update state
    update_state("0", "done")

    # Verify
    updated = load_session("0")
    assert updated.state == "done"


def test_update_state_not_found(mock_scope_base):
    """Test update_state raises FileNotFoundError for missing session."""
    with pytest.raises(FileNotFoundError):
        update_state("999", "aborted")


def test_delete_session_function(mock_scope_base):
    """Test delete_session function."""
    # Create a session
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Delete it
    delete_session("0")

    # Verify it's gone
    assert load_session("0") is None


def test_delete_session_not_found(mock_scope_base):
    """Test delete_session raises FileNotFoundError for missing session."""
    with pytest.raises(FileNotFoundError):
        delete_session("999")


def test_get_descendants_empty(mock_scope_base):
    """Test get_descendants returns empty list when no children."""
    # Create a session with no children
    session = Session(
        id="0",
        task="Parent",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    descendants = get_descendants("0")
    assert descendants == []


def test_get_descendants_with_children(mock_scope_base):
    """Test get_descendants finds all children."""
    # Create parent and children
    for session_id, parent in [("0", ""), ("0.0", "0"), ("0.1", "0"), ("0.0.0", "0.0")]:
        session = Session(
            id=session_id,
            task=f"Task {session_id}",
            parent=parent,
            state="running",
            tmux_session=f"scope-{session_id}",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

    descendants = get_descendants("0")
    descendant_ids = [s.id for s in descendants]

    # Should include all children but not the parent itself
    assert "0" not in descendant_ids
    assert "0.0" in descendant_ids
    assert "0.1" in descendant_ids
    assert "0.0.0" in descendant_ids

    # Should be sorted deepest-first
    assert descendant_ids.index("0.0.0") < descendant_ids.index("0.0")


def test_abort_with_children_confirmation_declined(runner, mock_scope_base, cleanup_scope_windows):
    """Test abort with children shows confirmation and can be declined."""
    # Create parent and child
    for session_id, parent in [("0", ""), ("0.0", "0")]:
        session = Session(
            id=session_id,
            task=f"Task {session_id}",
            parent=parent,
            state="running",
            tmux_session=f"scope-{session_id}",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

    # Decline confirmation
    result = runner.invoke(main, ["abort", "0"], input="n\n")
    assert result.exit_code == 0
    assert "1 child session" in result.output
    assert "0.0" in result.output

    # Sessions should still exist
    assert load_session("0") is not None
    assert load_session("0.0") is not None


def test_abort_with_children_confirmation_accepted(runner, mock_scope_base, cleanup_scope_windows):
    """Test abort with children deletes all when confirmed."""
    # Create parent and children
    for session_id, parent in [("0", ""), ("0.0", "0"), ("0.1", "0")]:
        session = Session(
            id=session_id,
            task=f"Task {session_id}",
            parent=parent,
            state="running",
            tmux_session=f"scope-{session_id}",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

    # Accept confirmation
    result = runner.invoke(main, ["abort", "0"], input="y\n")
    assert result.exit_code == 0
    assert "Aborted child session 0.0" in result.output or "Aborted child session 0.1" in result.output
    assert "Aborted session 0" in result.output

    # All sessions should be deleted
    assert load_session("0") is None
    assert load_session("0.0") is None
    assert load_session("0.1") is None


def test_abort_with_children_yes_flag(runner, mock_scope_base, cleanup_scope_windows):
    """Test abort -y skips confirmation."""
    # Create parent and child
    for session_id, parent in [("0", ""), ("0.0", "0")]:
        session = Session(
            id=session_id,
            task=f"Task {session_id}",
            parent=parent,
            state="running",
            tmux_session=f"scope-{session_id}",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

    # Use -y flag
    result = runner.invoke(main, ["abort", "0", "-y"])
    assert result.exit_code == 0
    assert "Abort all these sessions?" not in result.output  # No confirmation prompt
    assert "Aborted child session 0.0" in result.output
    assert "Aborted session 0" in result.output

    # All sessions should be deleted
    assert load_session("0") is None
    assert load_session("0.0") is None


def test_abort_without_children_no_confirmation(runner, mock_scope_base, cleanup_scope_windows):
    """Test abort without children doesn't show confirmation."""
    # Create session without children
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["abort", "0"])
    assert result.exit_code == 0
    assert "child session" not in result.output
    assert "Aborted session 0" in result.output
    assert load_session("0") is None


def window_exists(session_name: str, window_name: str) -> bool:
    """Check if a tmux window exists in a session."""
    result = subprocess.run(
        tmux_cmd(["list-windows", "-t", session_name, "-F", "#{window_name}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    windows = result.stdout.strip().split("\n")
    return window_name in windows


@pytest.mark.skipif(not tmux_available(), reason="tmux not installed")
def test_abort_kills_tmux_window(runner, mock_scope_base, cleanup_scope_windows):
    """Test abort kills the tmux window in the scope session."""

    # Get the scope session name from env (set by cleanup_scope_windows)
    import os
    scope_session = os.environ.get("SCOPE_TMUX_SESSION", "scope")

    # Ensure the scope session exists
    subprocess.run(
        tmux_cmd(["new-session", "-d", "-s", scope_session]),
        capture_output=True,
    )

    # Create a window in the scope session (simulating a session running as a window)
    subprocess.run(
        tmux_cmd(["new-window", "-d", "-t", scope_session, "-n", "w0", "cat"]),
        capture_output=True,
    )
    assert window_exists(scope_session, "w0")

    # Create session state
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["abort", "0"])
    assert result.exit_code == 0

    # Verify tmux window was killed
    assert not window_exists(scope_session, "w0")

    # Verify session was deleted
    assert load_session("0") is None
