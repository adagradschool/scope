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
    assert "Resume a completed scope session" in result.output


def test_resume_session_not_found(runner, mock_scope_base):
    """Test resume with non-existent session."""
    result = runner.invoke(main, ["resume", "999"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_resume_non_done_session(runner, mock_scope_base):
    """Test resume rejects non-done session."""
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
    assert "not done" in result.output


def test_resume_without_claude_uuid(runner, mock_scope_base):
    """Test resume fails when no Claude UUID saved."""
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
    assert "no claude session uuid" in result.output.lower()


def test_resume_by_alias(runner, mock_scope_base):
    """Test resume resolves alias."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
        alias="my-task",
    )
    save_session(session)

    result = runner.invoke(main, ["resume", "my-task"])
    # Will fail because no UUID, but proves alias resolution works
    assert result.exit_code == 1
    assert "no claude session uuid" in result.output.lower()


def test_resume_done_session(runner, mock_scope_base, monkeypatch, cleanup_scope_windows):
    """Test resuming a done session creates tmux window."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
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

    result = runner.invoke(main, ["resume", "0"])

    assert result.exit_code == 0
    assert "Resumed session 0" in result.output
    assert len(created_windows) == 1
    assert "--resume" in created_windows[0]["command"]
    assert "04cad4c6-1aee-4ac7-b38c-596edda8e3e5" in created_windows[0]["command"]


def test_resume_keeps_state_done(runner, mock_scope_base, monkeypatch, cleanup_scope_windows):
    """Test resuming keeps state as done."""
    from scope.core.state import load_session

    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    save_claude_session_id("0", "04cad4c6-1aee-4ac7-b38c-596edda8e3e5")

    # Mock tmux functions
    monkeypatch.setattr(
        "scope.commands.resume.has_window_in_session", lambda s, w: False
    )
    monkeypatch.setattr("scope.commands.resume.create_window", lambda **kw: None)
    monkeypatch.setattr("scope.commands.resume.set_pane_option", lambda *args: None)
    monkeypatch.setattr("scope.commands.resume.install_tmux_hooks", lambda: None)

    result = runner.invoke(main, ["resume", "0"])

    assert result.exit_code == 0
    loaded = load_session("0")
    assert loaded.state == "done"


def test_resume_window_already_exists_recovers(runner, mock_scope_base, monkeypatch):
    """Test resume recovers when window already exists for done session."""
    from scope.core.state import load_session as load_session_fn

    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    save_claude_session_id("0", "04cad4c6-1aee-4ac7-b38c-596edda8e3e5")

    # Mock window check to return true (window exists from prior partial resume)
    monkeypatch.setattr(
        "scope.commands.resume.has_window_in_session", lambda s, w: True
    )
    monkeypatch.setattr(
        "scope.commands.resume.get_scope_session", lambda: "scope-test"
    )

    result = runner.invoke(main, ["resume", "0"])

    assert result.exit_code == 0
    assert "recovered existing window" in result.output
    loaded = load_session_fn("0")
    assert loaded.state == "done"
