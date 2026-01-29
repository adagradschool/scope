"""Tests for the resume command."""

from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.core.session import Session
from scope.core.state import save_session, save_claude_session_id


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


def test_resume_help(runner):
    """Test resume command shows help."""
    result = runner.invoke(main, ["resume", "--help"])
    assert result.exit_code == 0
    assert "Resume an evicted scope session" in result.output


def test_resume_session_not_found(runner, mock_scope_base):
    """Test resume with non-existent session."""
    result = runner.invoke(main, ["resume", "999"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_resume_non_evicted_session(runner, mock_scope_base):
    """Test resume rejects non-evicted session."""
    # Create a running session
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="running",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["resume", "0"])
    assert result.exit_code == 1
    assert "not evicted" in result.output


def test_resume_done_session_rejected(runner, mock_scope_base):
    """Test resume rejects done session."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["resume", "0"])
    assert result.exit_code == 1
    assert "not evicted" in result.output


def test_resume_without_claude_uuid(runner, mock_scope_base):
    """Test resume fails when no Claude UUID saved."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="evicted",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["resume", "0"])
    assert result.exit_code == 1
    assert "no claude session uuid" in result.output.lower()


def test_resume_by_alias(runner, mock_scope_base):
    """Test resume resolves alias."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="evicted",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
        alias="my-task",
    )
    save_session(session)

    result = runner.invoke(main, ["resume", "my-task"])
    # Will fail because no UUID, but proves alias resolution works
    assert result.exit_code == 1
    assert "no claude session uuid" in result.output.lower()


def test_resume_evicted_session(runner, mock_scope_base, monkeypatch, cleanup_scope_windows):
    """Test resuming an evicted session creates tmux window."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="evicted",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    save_claude_session_id("0", "04cad4c6-1aee-4ac7-b38c-596edda8e3e5")

    # Mock tmux window check to return false (window doesn't exist)
    monkeypatch.setattr(
        "scope.commands.resume.has_window_in_session", lambda s, w: False
    )

    # Track created windows
    created_windows = []

    def mock_create_window(name, command, cwd, env):
        created_windows.append({"name": name, "command": command})

    monkeypatch.setattr("scope.commands.resume.create_window", mock_create_window)
    monkeypatch.setattr("scope.commands.resume.set_pane_option", lambda *args: None)
    monkeypatch.setattr("scope.commands.resume.install_tmux_hooks", lambda: None)

    # Mock LRU functions
    monkeypatch.setattr("scope.commands.resume.remove_session", lambda p, s: None)
    monkeypatch.setattr(
        "scope.commands.resume.get_project_identifier", lambda: "test-project"
    )

    result = runner.invoke(main, ["resume", "0"])

    assert result.exit_code == 0
    assert "Resumed session 0" in result.output
    assert len(created_windows) == 1
    assert "--resume" in created_windows[0]["command"]
    assert "04cad4c6-1aee-4ac7-b38c-596edda8e3e5" in created_windows[0]["command"]


def test_resume_updates_state_to_running(runner, mock_scope_base, monkeypatch, cleanup_scope_windows):
    """Test resuming updates state from evicted to running."""
    from scope.core.state import load_session

    session = Session(
        id="0",
        task="Test",
        parent="",
        state="evicted",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    save_claude_session_id("0", "04cad4c6-1aee-4ac7-b38c-596edda8e3e5")

    # Mock tmux and LRU functions
    monkeypatch.setattr(
        "scope.commands.resume.has_window_in_session", lambda s, w: False
    )
    monkeypatch.setattr("scope.commands.resume.create_window", lambda **kw: None)
    monkeypatch.setattr("scope.commands.resume.set_pane_option", lambda *args: None)
    monkeypatch.setattr("scope.commands.resume.install_tmux_hooks", lambda: None)
    monkeypatch.setattr("scope.commands.resume.remove_session", lambda p, s: None)
    monkeypatch.setattr(
        "scope.commands.resume.get_project_identifier", lambda: "test-project"
    )

    result = runner.invoke(main, ["resume", "0"])

    assert result.exit_code == 0
    loaded = load_session("0")
    assert loaded.state == "running"


def test_resume_window_already_exists(runner, mock_scope_base, monkeypatch):
    """Test resume fails if window already exists."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="evicted",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    save_claude_session_id("0", "04cad4c6-1aee-4ac7-b38c-596edda8e3e5")

    # Mock window check to return true (window exists)
    monkeypatch.setattr(
        "scope.commands.resume.has_window_in_session", lambda s, w: True
    )
    monkeypatch.setattr(
        "scope.commands.resume.get_scope_session", lambda: "scope-test"
    )

    result = runner.invoke(main, ["resume", "0"])

    assert result.exit_code == 1
    assert "already exists" in result.output
