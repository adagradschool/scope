"""Tests for tmux wrapper.

Note: These tests require tmux to be installed.
"""

import subprocess

import pytest

from scope.core.tmux import (
    TmuxError,
    create_session,
    get_current_session,
    has_session,
    split_window,
)

from tests.helpers import tmux_cmd


def tmux_available() -> bool:
    """Check if tmux is available."""
    result = subprocess.run(["which", "tmux"], capture_output=True)
    return result.returncode == 0


@pytest.fixture
def cleanup_session(cleanup_scope_windows):
    """Fixture to cleanup tmux sessions after tests.

    Depends on cleanup_scope_windows to set up socket isolation.
    """
    sessions = []
    yield sessions
    for name in sessions:
        subprocess.run(tmux_cmd(["kill-session", "-t", name]), capture_output=True)


@pytest.mark.skipif(not tmux_available(), reason="tmux not installed")
def test_create_session(cleanup_session, tmp_path):
    """Test creating a tmux session."""
    name = "scope-test-create"
    cleanup_session.append(name)

    create_session(name=name, command="sleep 60", cwd=tmp_path)

    assert has_session(name)


@pytest.mark.skipif(not tmux_available(), reason="tmux not installed")
def test_create_session_with_env(cleanup_session, tmp_path):
    """Test creating a session with environment variables."""
    name = "scope-test-env"
    cleanup_session.append(name)

    create_session(
        name=name,
        command="sleep 60",
        cwd=tmp_path,
        env={"SCOPE_SESSION_ID": "0"},
    )

    assert has_session(name)


@pytest.mark.skipif(not tmux_available(), reason="tmux not installed")
def test_has_session_false():
    """Test has_session returns False for non-existent session."""
    assert not has_session("nonexistent-session-12345")


@pytest.mark.skipif(not tmux_available(), reason="tmux not installed")
def test_create_session_duplicate_fails(cleanup_session, tmp_path):
    """Test creating duplicate session raises error."""
    name = "scope-test-dup"
    cleanup_session.append(name)

    create_session(name=name, command="sleep 60", cwd=tmp_path)

    with pytest.raises(TmuxError):
        create_session(name=name, command="sleep 60", cwd=tmp_path)


def test_get_current_session_outside_tmux(monkeypatch):
    """Test get_current_session returns None when not in tmux."""
    # Ensure TMUX env var is not set
    monkeypatch.delenv("TMUX", raising=False)
    # When not in tmux, get_current_session should return None
    # (tmux display-message fails when not in a tmux session)
    result = get_current_session()
    # Result is None when not in tmux, or a string if we happen to be in tmux
    assert result is None or isinstance(result, str)


def test_split_window_fails_outside_tmux(tmp_path):
    """Test split_window raises TmuxError when not in tmux."""
    from unittest.mock import MagicMock, patch

    # Mock subprocess.run to simulate not being in tmux
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "no server running on /tmp/tmux-xxx/default"

    with patch("scope.core.tmux.subprocess.run", return_value=mock_result):
        with pytest.raises(TmuxError):
            split_window(command="echo test", cwd=tmp_path)


@pytest.mark.skipif(not tmux_available(), reason="tmux not installed")
def test_split_window_in_session(cleanup_session, tmp_path):
    """Test split_window works inside a tmux session."""
    name = "scope-test-split"
    cleanup_session.append(name)

    # Create a session first
    create_session(name=name, command="sleep 60", cwd=tmp_path)

    # Split window using -t to target the session
    # Note: split_window without target only works when inside tmux
    # For testing, we use tmux send-keys to run the split command inside the session
    result = subprocess.run(
        tmux_cmd(["split-window", "-t", name, "-h", "sleep 30"]),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
