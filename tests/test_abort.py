"""Tests for abort command."""

import subprocess
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.core.session import Session
from scope.core.state import delete_session, load_session, save_session, update_state


def tmux_available() -> bool:
    """Check if tmux is available."""
    result = subprocess.run(["which", "tmux"], capture_output=True)
    return result.returncode == 0


def session_exists(session_name: str) -> bool:
    """Check if a tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
    )
    return result.returncode == 0


@pytest.fixture
def cleanup_scope_sessions():
    """Fixture to cleanup scope tmux sessions before and after tests."""
    for i in range(10):
        subprocess.run(["tmux", "kill-session", "-t", f"scope-{i}"], capture_output=True)
    yield
    for i in range(10):
        subprocess.run(["tmux", "kill-session", "-t", f"scope-{i}"], capture_output=True)


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_abort_help(runner):
    """Test abort --help shows usage."""
    result = runner.invoke(main, ["abort", "--help"])
    assert result.exit_code == 0
    assert "Abort a scope session" in result.output


def test_abort_session_not_found(runner, tmp_path, monkeypatch):
    """Test aborting non-existent session shows error."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(main, ["abort", "999"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_abort_deletes_session(runner, tmp_path, monkeypatch):
    """Test abort deletes the session."""
    monkeypatch.chdir(tmp_path)

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
def test_abort_kills_tmux_session(runner, tmp_path, monkeypatch, cleanup_scope_sessions):
    """Test abort kills the tmux session."""
    monkeypatch.chdir(tmp_path)

    # Create a real tmux session
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", "scope-0", "cat"],
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


def test_update_state_function(tmp_path, monkeypatch):
    """Test update_state function."""
    monkeypatch.chdir(tmp_path)

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


def test_update_state_not_found(tmp_path, monkeypatch):
    """Test update_state raises FileNotFoundError for missing session."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError):
        update_state("999", "aborted")


def test_delete_session_function(tmp_path, monkeypatch):
    """Test delete_session function."""
    monkeypatch.chdir(tmp_path)

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


def test_delete_session_not_found(tmp_path, monkeypatch):
    """Test delete_session raises FileNotFoundError for missing session."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError):
        delete_session("999")
