"""Tests for spawn command."""

import os
import subprocess

import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.commands.spawn import PENDING_TASK
from tests.helpers import tmux_cmd


def window_exists(window_name: str) -> bool:
    """Check if a tmux window exists in the test session.

    Uses SCOPE_TMUX_SESSION env var (set by cleanup_scope_windows fixture) for isolation.
    """
    session = os.environ.get("SCOPE_TMUX_SESSION", "scope-test")
    result = subprocess.run(
        tmux_cmd(["list-windows", "-t", session, "-F", "#{window_name}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    windows = result.stdout.strip().split("\n")
    return window_name in windows


# Note: cleanup_scope_windows is imported from conftest.py


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_spawn_no_args(runner):
    """Test spawn without prompt argument shows error."""
    result = runner.invoke(main, ["spawn"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_spawn_help(runner):
    """Test spawn --help shows usage."""
    result = runner.invoke(main, ["spawn", "--help"])
    assert result.exit_code == 0
    assert "Spawn a new scope session" in result.output


def test_spawn_creates_session(runner, mock_scope_base, cleanup_scope_windows):
    """Test spawn creates session files and tmux window."""
    result = runner.invoke(main, ["spawn", "Write tests for auth module"])

    assert result.exit_code == 0
    session_id = result.output.strip()
    assert session_id == "0"

    # Verify filesystem
    session_dir = mock_scope_base / "sessions" / "0"
    assert session_dir.exists()
    # Task starts as pending, will be inferred by hooks
    assert (session_dir / "task").read_text() == PENDING_TASK
    assert (session_dir / "state").read_text() == "running"
    # Contract should contain the prompt with # Task header
    contract = (session_dir / "contract.md").read_text()
    assert "# Task" in contract
    assert "Write tests for auth module" in contract

    # Verify tmux window exists in the scope session
    assert window_exists("w0")


def test_spawn_sequential_ids(runner, mock_scope_base, cleanup_scope_windows):
    """Test multiple spawns get sequential IDs."""
    result1 = runner.invoke(main, ["spawn", "Task 1"])
    result2 = runner.invoke(main, ["spawn", "Task 2"])

    assert result1.output.strip() == "0"
    assert result2.output.strip() == "1"


def test_spawn_with_parent(runner, mock_scope_base, monkeypatch, cleanup_scope_windows):
    """Test spawn with SCOPE_SESSION_ID creates child session."""
    monkeypatch.setenv("SCOPE_SESSION_ID", "0")

    # Create parent directory first
    (mock_scope_base / "sessions" / "0").mkdir(parents=True)

    result = runner.invoke(main, ["spawn", "Child task prompt"])

    assert result.exit_code == 0
    session_id = result.output.strip()
    assert session_id == "0.0"

    # Verify parent is set correctly
    session_dir = mock_scope_base / "sessions" / "0.0"
    assert (session_dir / "parent").read_text() == "0"
    # Contract should contain the prompt
    contract = (session_dir / "contract.md").read_text()
    assert "# Task" in contract
    assert "Child task prompt" in contract
