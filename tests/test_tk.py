"""Tests for scope tk proxy command."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.core.session import Session
from scope.core.state import save_session


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def _create_session(session_id: str, alias: str = "") -> Session:
    return Session(
        id=session_id,
        task="test task",
        parent="",
        state="running",
        tmux_session=f"w{session_id}",
        created_at=datetime.now(timezone.utc),
        alias=alias,
    )


def test_tk_requires_session(runner):
    """Test tk fails when no session context is provided."""
    result = runner.invoke(main, ["tk", "ls"])
    assert result.exit_code != 0
    assert "No session specified" in result.output


def test_tk_uses_env_session(runner, mock_scope_base, monkeypatch):
    """Test tk uses $SCOPE_SESSION_ID and sets TICKETS_DIR."""
    session = _create_session("0")
    save_session(session)
    monkeypatch.setenv("SCOPE_SESSION_ID", "0")

    captured = {}

    def fake_run(*args, **kwargs):
        captured["args"] = args[0]
        captured["env"] = kwargs.get("env")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("scope.commands.tk.subprocess.run", fake_run)

    result = runner.invoke(main, ["tk", "ls"])
    assert result.exit_code == 0
    assert captured["args"] == ["tk", "ls"]
    expected_dir = mock_scope_base / "sessions" / "0" / ".tickets"
    assert captured["env"]["TICKETS_DIR"] == str(expected_dir)
    assert expected_dir.exists()


def test_tk_resolves_alias(runner, mock_scope_base, monkeypatch):
    """Test tk resolves session alias via --session."""
    session = _create_session("1", alias="alpha")
    save_session(session)

    captured = {}

    def fake_run(*args, **kwargs):
        captured["args"] = args[0]
        captured["env"] = kwargs.get("env")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("scope.commands.tk.subprocess.run", fake_run)

    result = runner.invoke(main, ["tk", "--session", "alpha", "create", "Task"])
    assert result.exit_code == 0
    assert captured["args"] == ["tk", "create", "Task"]
    expected_dir = mock_scope_base / "sessions" / "1" / ".tickets"
    assert captured["env"]["TICKETS_DIR"] == str(expected_dir)
    assert expected_dir.exists()


def test_tk_propagates_exit_code(runner, mock_scope_base, monkeypatch):
    """Test tk propagates subprocess exit codes."""
    session = _create_session("2")
    save_session(session)
    monkeypatch.setenv("SCOPE_SESSION_ID", "2")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=3)

    monkeypatch.setattr("scope.commands.tk.subprocess.run", fake_run)

    result = runner.invoke(main, ["tk", "ls"])
    assert result.exit_code == 3
