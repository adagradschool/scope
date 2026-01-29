"""Tests for poll command."""

from datetime import datetime, timezone

import orjson
import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.core.session import Session
from scope.core.state import save_session


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_poll_help(runner):
    """Test poll --help shows usage."""
    result = runner.invoke(main, ["poll", "--help"])
    assert result.exit_code == 0
    assert "Poll session status" in result.output


def test_poll_no_args(runner):
    """Test poll without session_id or --all shows error."""
    result = runner.invoke(main, ["poll"])
    assert result.exit_code == 1
    assert "provide session IDs or use --all" in result.output


def test_poll_session_not_found(runner, mock_scope_base):
    """Test poll with non-existent session returns error."""
    result = runner.invoke(main, ["poll", "999"])

    assert result.exit_code == 1
    assert "Session 999 not found" in result.output


def test_poll_running_session(runner, mock_scope_base):
    """Test poll returns compact status for running session."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["poll", "0"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["status"] == "running"
    assert "elapsed" in data
    assert "tool_calls" in data


def test_poll_done_session(runner, mock_scope_base):
    """Test poll returns status for completed session."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["poll", "0"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["status"] == "done"
    assert "elapsed" in data


def test_poll_with_activity(runner, mock_scope_base):
    """Test poll returns activity when present."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Write activity file
    activity_file = mock_scope_base / "sessions" / "0" / "activity"
    activity_file.write_text("editing src/auth.ts")

    result = runner.invoke(main, ["poll", "0"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["status"] == "running"
    assert data["activity"] == "editing src/auth.ts"


def test_poll_compact_no_result(runner, mock_scope_base):
    """Test poll output does NOT include result text (use wait for that)."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Write result file
    result_file = mock_scope_base / "sessions" / "0" / "result"
    result_file.write_text("Completed successfully. Updated 3 files.")

    result = runner.invoke(main, ["poll", "0"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["status"] == "done"
    # Poll should NOT include result text — that belongs to wait
    assert "result" not in data


def test_poll_elapsed_time(runner, mock_scope_base):
    """Test poll includes elapsed time since session creation."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["poll", "0"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    # Elapsed should be a short string like "0s" or "1s"
    assert "elapsed" in data
    assert data["elapsed"].endswith("s")


def test_poll_tool_calls_count(runner, mock_scope_base):
    """Test poll includes tool call count from trajectory index."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Write a trajectory index with tool calls
    index_file = mock_scope_base / "sessions" / "0" / "trajectory_index.json"
    index_data = {
        "turn_count": 5,
        "tool_calls": ["Read", "Grep", "Edit", "Read", "Bash"],
        "tool_summary": {"Read": 2, "Grep": 1, "Edit": 1, "Bash": 1},
    }
    index_file.write_bytes(orjson.dumps(index_data))

    result = runner.invoke(main, ["poll", "0"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["tool_calls"] == 5


def test_poll_tool_calls_zero_without_index(runner, mock_scope_base):
    """Test poll returns 0 tool calls when no trajectory index exists."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["poll", "0"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["tool_calls"] == 0


def test_poll_child_session(runner, mock_scope_base):
    """Test poll works with child session IDs."""
    session = Session(
        id="0.1",
        task="Child task",
        parent="0",
        state="running",
        tmux_session="scope-0.1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["poll", "0.1"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["status"] == "running"


def test_poll_evicted_session(runner, mock_scope_base):
    """Test poll returns status for evicted session."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="evicted",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["poll", "0"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["status"] == "evicted"


def test_poll_evicted_activity_past_tense(runner, mock_scope_base):
    """Test poll converts activity to past tense for evicted session."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="evicted",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Write activity file with present tense
    activity_file = mock_scope_base / "sessions" / "0" / "activity"
    activity_file.write_text("reading src/auth.ts")

    result = runner.invoke(main, ["poll", "0"])

    assert result.exit_code == 0
    data = orjson.loads(result.output)
    assert data["status"] == "evicted"
    assert data["activity"] == "read src/auth.ts"


def test_poll_all_sessions(runner, mock_scope_base):
    """Test poll --all returns status for all sessions."""
    for i in range(3):
        session = Session(
            id=str(i),
            task=f"Task {i}",
            parent="",
            state="running" if i < 2 else "done",
            tmux_session=f"scope-{i}",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

    result = runner.invoke(main, ["poll", "--all"])

    assert result.exit_code == 0
    lines = result.output.strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        data = orjson.loads(line)
        assert "id" in data
        assert "status" in data
        assert "elapsed" in data
        assert "tool_calls" in data


def test_poll_all_no_sessions(runner, mock_scope_base):
    """Test poll --all with no sessions shows error."""
    result = runner.invoke(main, ["poll", "--all"])

    assert result.exit_code == 1
    assert "No sessions found" in result.output


def test_poll_one_line_per_session(runner, mock_scope_base):
    """Test poll output is one JSON object per line (compact for orchestrator context)."""
    for i in range(2):
        session = Session(
            id=str(i),
            task=f"Task {i}",
            parent="",
            state="running",
            tmux_session=f"scope-{i}",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

    result = runner.invoke(main, ["poll", "0", "1"])

    assert result.exit_code == 0
    lines = result.output.strip().split("\n")
    assert len(lines) == 2
    # Each line should be valid JSON
    for line in lines:
        data = orjson.loads(line)
        assert isinstance(data, dict)
