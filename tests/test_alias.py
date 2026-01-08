"""Tests for alias functionality."""

from datetime import datetime, timezone

import orjson
import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.core.session import Session
from scope.core.state import (
    load_session,
    load_session_by_alias,
    resolve_id,
    save_session,
)


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


# --- Unit tests for state.py alias functions ---


def test_save_session_writes_alias_file(mock_scope_base):
    """Test that save_session writes the alias file."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="my-task",
    )
    save_session(session)

    alias_file = mock_scope_base / "sessions" / "0" / "alias"
    assert alias_file.exists()
    assert alias_file.read_text() == "my-task"


def test_save_session_writes_empty_alias(mock_scope_base):
    """Test that save_session writes empty alias file when no alias."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    alias_file = mock_scope_base / "sessions" / "0" / "alias"
    assert alias_file.exists()
    assert alias_file.read_text() == ""


def test_load_session_reads_alias(mock_scope_base):
    """Test that load_session reads the alias field."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="my-task",
    )
    save_session(session)

    loaded = load_session("0")
    assert loaded is not None
    assert loaded.alias == "my-task"


def test_load_session_handles_missing_alias_file(mock_scope_base):
    """Test that load_session handles sessions without alias file (backward compat)."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Remove alias file to simulate old session
    alias_file = mock_scope_base / "sessions" / "0" / "alias"
    alias_file.unlink()

    loaded = load_session("0")
    assert loaded is not None
    assert loaded.alias == ""


def test_load_session_by_alias_found(mock_scope_base):
    """Test load_session_by_alias returns session when alias exists."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="my-task",
    )
    save_session(session)

    loaded = load_session_by_alias("my-task")
    assert loaded is not None
    assert loaded.id == "0"
    assert loaded.alias == "my-task"


def test_load_session_by_alias_not_found(mock_scope_base):
    """Test load_session_by_alias returns None when alias doesn't exist."""
    loaded = load_session_by_alias("nonexistent")
    assert loaded is None


def test_load_session_by_alias_empty(mock_scope_base):
    """Test load_session_by_alias returns None for empty alias."""
    loaded = load_session_by_alias("")
    assert loaded is None


def test_resolve_id_with_numeric_id(mock_scope_base):
    """Test resolve_id returns ID when given numeric session ID."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    resolved = resolve_id("0")
    assert resolved == "0"


def test_resolve_id_with_alias(mock_scope_base):
    """Test resolve_id returns ID when given alias."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="my-task",
    )
    save_session(session)

    resolved = resolve_id("my-task")
    assert resolved == "0"


def test_resolve_id_not_found(mock_scope_base):
    """Test resolve_id returns None when neither ID nor alias exists."""
    resolved = resolve_id("nonexistent")
    assert resolved is None


def test_resolve_id_prefers_numeric_id_over_alias(mock_scope_base):
    """Test resolve_id checks numeric ID first before alias."""
    # Create session with ID "0" and alias "1"
    session0 = Session(
        id="0",
        task="Task 0",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="1",
    )
    # Create session with ID "1"
    session1 = Session(
        id="1",
        task="Task 1",
        parent="",
        state="running",
        tmux_session="scope-1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session0)
    save_session(session1)

    # Resolve "1" should return "1" (the numeric ID), not "0" (which has alias "1")
    resolved = resolve_id("1")
    assert resolved == "1"


# --- CLI tests for spawn --id ---


def test_spawn_with_id_creates_alias_file(runner, mock_scope_base, cleanup_scope_windows):
    """Test spawn --id creates alias file."""
    result = runner.invoke(main, ["spawn", "--id", "foo", "Test task"])

    # Debug output for CI failures
    if result.exit_code != 0:
        import sys
        print(f"\n=== SPAWN FAILED ===", file=sys.stderr)
        print(f"exit_code: {result.exit_code}", file=sys.stderr)
        print(f"output: {result.output}", file=sys.stderr)
        if result.exception:
            import traceback
            print(f"exception: {result.exception}", file=sys.stderr)
            print("".join(traceback.format_exception(type(result.exception), result.exception, result.exception.__traceback__)), file=sys.stderr)
        print(f"=== END SPAWN DEBUG ===\n", file=sys.stderr)

    assert result.exit_code == 0
    session_id = result.output.strip()

    alias_file = mock_scope_base / "sessions" / session_id / "alias"
    assert alias_file.exists()
    assert alias_file.read_text() == "foo"


def test_spawn_duplicate_alias_rejected(runner, mock_scope_base, cleanup_scope_windows):
    """Test spawn rejects duplicate alias."""
    # First spawn with alias
    result1 = runner.invoke(main, ["spawn", "--id", "foo", "First task"])
    assert result1.exit_code == 0

    # Second spawn with same alias should fail
    result2 = runner.invoke(main, ["spawn", "--id", "foo", "Second task"])
    assert result2.exit_code == 1
    assert "alias 'foo' is already used by session" in result2.output


# --- CLI tests for poll with alias ---


def test_poll_with_alias(runner, mock_scope_base):
    """Test poll works with alias lookup."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="my-task",
    )
    save_session(session)

    result = runner.invoke(main, ["poll", "my-task"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["status"] == "running"


def test_poll_with_alias_not_found(runner, mock_scope_base):
    """Test poll returns error for unknown alias."""
    result = runner.invoke(main, ["poll", "nonexistent"])

    assert result.exit_code == 1
    assert "Session nonexistent not found" in result.output


# --- CLI tests for wait with alias ---


def test_wait_with_alias(runner, mock_scope_base):
    """Test wait works with alias lookup."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="my-task",
    )
    save_session(session)

    result = runner.invoke(main, ["wait", "my-task"])

    assert result.exit_code == 0


def test_wait_with_mixed_ids_and_aliases(runner, mock_scope_base):
    """Test wait works with mix of IDs and aliases."""
    session0 = Session(
        id="0",
        task="Task 0",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="first",
    )
    session1 = Session(
        id="1",
        task="Task 1",
        parent="",
        state="done",
        tmux_session="scope-1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session0)
    save_session(session1)

    # Wait using alias for first, numeric ID for second
    result = runner.invoke(main, ["wait", "first", "1"])

    assert result.exit_code == 0
