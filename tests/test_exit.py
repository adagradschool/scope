"""Tests for scope exit command and exit reason state helpers."""

from datetime import datetime, timezone

from click.testing import CliRunner

from scope.commands.exit import exit_cmd
from scope.core.session import Session
from scope.core.state import (
    load_exit_reason,
    load_session,
    save_exit_reason,
    save_session,
)


def _make_session(session_id: str = "0") -> Session:
    return Session(
        id=session_id,
        task="test task",
        parent="",
        state="running",
        tmux_session="scope-test",
        created_at=datetime.now(timezone.utc),
        alias="",
    )


def test_save_and_load_exit_reason(mock_scope_base):
    """save_exit_reason / load_exit_reason round-trip."""
    session = _make_session()
    save_session(session)

    save_exit_reason("0", "needs redesign")
    assert load_exit_reason("0") == "needs redesign"


def test_load_exit_reason_returns_none_for_nonexistent(mock_scope_base):
    """load_exit_reason returns None when session has no exit_reason file."""
    session = _make_session()
    save_session(session)

    assert load_exit_reason("0") is None


def test_load_exit_reason_returns_none_for_missing_session(mock_scope_base):
    """load_exit_reason returns None when the session dir doesn't exist."""
    assert load_exit_reason("999") is None


def test_exit_cmd_sets_state_and_reason(mock_scope_base, monkeypatch):
    """scope exit sets state to 'exited' and saves the reason."""
    session = _make_session()
    save_session(session)

    monkeypatch.setenv("SCOPE_SESSION_ID", "0")

    runner = CliRunner()
    result = runner.invoke(exit_cmd, ["needs redesign"])

    assert result.exit_code == 0
    assert "exited" in result.output

    loaded = load_session("0")
    assert loaded is not None
    assert loaded.state == "exited"
    assert load_exit_reason("0") == "needs redesign"


def test_exit_cmd_no_session_id(mock_scope_base, monkeypatch):
    """scope exit fails when SCOPE_SESSION_ID is not set."""
    monkeypatch.delenv("SCOPE_SESSION_ID", raising=False)

    runner = CliRunner()
    result = runner.invoke(exit_cmd, ["some reason"])

    assert result.exit_code == 1
    assert "SCOPE_SESSION_ID not set" in result.output


def test_exit_cmd_missing_session(mock_scope_base, monkeypatch):
    """scope exit fails when session doesn't exist."""
    monkeypatch.setenv("SCOPE_SESSION_ID", "999")

    runner = CliRunner()
    result = runner.invoke(exit_cmd, ["some reason"])

    assert result.exit_code == 1
    assert "not found" in result.output
