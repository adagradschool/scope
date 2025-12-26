"""Tests for wait command."""

import threading
import time
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.core.session import Session
from scope.core.state import save_failed_reason, save_session, update_state


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_wait_help(runner):
    """Test wait --help shows usage."""
    result = runner.invoke(main, ["wait", "--help"])
    assert result.exit_code == 0
    assert "Wait for session(s) to complete" in result.output


def test_wait_no_args(runner):
    """Test wait without session_id shows error."""
    result = runner.invoke(main, ["wait"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_wait_session_not_found(runner, mock_scope_base):
    """Test wait with non-existent session returns error."""
    result = runner.invoke(main, ["wait", "999"])

    assert result.exit_code == 1
    assert "Session 999 not found" in result.output


def test_wait_already_done(runner, mock_scope_base):
    """Test wait returns immediately if session already done."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["wait", "0"])

    assert result.exit_code == 0
    assert result.output == ""  # No result file


def test_wait_already_aborted(runner, mock_scope_base):
    """Test wait returns immediately if session already aborted."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="aborted",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["wait", "0"])

    assert result.exit_code == 2  # Aborted exit code


def test_wait_with_result(runner, mock_scope_base):
    """Test wait outputs result file content."""
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
    result_file.write_text("Task completed successfully.")

    result = runner.invoke(main, ["wait", "0"])

    assert result.exit_code == 0
    assert result.output == "Task completed successfully."


def test_wait_blocks_until_done(runner, mock_scope_base):
    """Test wait blocks until session state changes to done."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Complete the session in a background thread after a delay
    def complete_session():
        time.sleep(0.3)
        update_state("0", "done")

    thread = threading.Thread(target=complete_session)
    thread.start()

    result = runner.invoke(main, ["wait", "0"])

    thread.join()

    assert result.exit_code == 0


def test_wait_child_session(runner, mock_scope_base):
    """Test wait works with child session IDs."""
    session = Session(
        id="0.1",
        task="Child task",
        parent="0",
        state="done",
        tmux_session="scope-0.1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["wait", "0.1"])

    assert result.exit_code == 0


def test_wait_multiple_sessions(runner, mock_scope_base):
    """Test wait works with multiple session IDs."""
    for i in range(3):
        session = Session(
            id=str(i),
            task=f"Task {i}",
            parent="",
            state="done",
            tmux_session=f"scope-{i}",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)
        result_file = mock_scope_base / "sessions" / str(i) / "result"
        result_file.write_text(f"Result {i}")

    result = runner.invoke(main, ["wait", "0", "1", "2"])

    assert result.exit_code == 0
    assert "[0]" in result.output
    assert "Result 0" in result.output
    assert "[1]" in result.output
    assert "Result 1" in result.output
    assert "[2]" in result.output
    assert "Result 2" in result.output


def test_wait_multiple_one_aborted(runner, mock_scope_base):
    """Test wait exits 2 if any session aborted."""
    session0 = Session(
        id="0",
        task="Task 0",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session0)

    session1 = Session(
        id="1",
        task="Task 1",
        parent="",
        state="aborted",
        tmux_session="scope-1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session1)

    result = runner.invoke(main, ["wait", "0", "1"])

    assert result.exit_code == 2


def test_wait_multiple_blocks_until_all_done(runner, mock_scope_base):
    """Test wait blocks until all sessions complete."""
    # Create two running sessions
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

    # Complete sessions in background threads
    def complete_session(sid, delay):
        time.sleep(delay)
        update_state(sid, "done")

    threads = [
        threading.Thread(target=complete_session, args=("0", 0.2)),
        threading.Thread(target=complete_session, args=("1", 0.4)),
    ]
    for t in threads:
        t.start()

    result = runner.invoke(main, ["wait", "0", "1"])

    for t in threads:
        t.join()

    assert result.exit_code == 0


def test_wait_multiple_with_aliases(runner, mock_scope_base):
    """Test multi-session wait includes alias in headers."""
    # Create sessions with aliases
    session0 = Session(
        id="0",
        task="Research task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="research",
    )
    save_session(session0)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Research results")

    session1 = Session(
        id="1",
        task="Audit task",
        parent="",
        state="done",
        tmux_session="scope-1",
        created_at=datetime.now(timezone.utc),
        alias="audit",
    )
    save_session(session1)
    (mock_scope_base / "sessions" / "1" / "result").write_text("Audit results")

    result = runner.invoke(main, ["wait", "0", "1"])

    assert result.exit_code == 0
    # Should include alias with ID in parentheses
    assert "[research (0)]" in result.output
    assert "Research results" in result.output
    assert "[audit (1)]" in result.output
    assert "Audit results" in result.output


def test_wait_multiple_without_aliases(runner, mock_scope_base):
    """Test multi-session wait shows just ID when no alias."""
    # Create sessions without aliases
    for i in range(2):
        session = Session(
            id=str(i),
            task=f"Task {i}",
            parent="",
            state="done",
            tmux_session=f"scope-{i}",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)
        (mock_scope_base / "sessions" / str(i) / "result").write_text(f"Result {i}")

    result = runner.invoke(main, ["wait", "0", "1"])

    assert result.exit_code == 0
    # Should show just ID in brackets (no alias)
    assert "[0]" in result.output
    assert "Result 0" in result.output
    assert "[1]" in result.output
    assert "Result 1" in result.output
    # Should NOT have alias format
    assert "(" not in result.output


def test_wait_single_no_header(runner, mock_scope_base):
    """Test single session wait has no header (backward compatible)."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="mytask",
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Task result")

    result = runner.invoke(main, ["wait", "0"])

    assert result.exit_code == 0
    # Single session should have NO header, even with alias
    assert "[" not in result.output
    assert "mytask" not in result.output
    assert result.output == "Task result"


def test_wait_multiple_mixed_aliases(runner, mock_scope_base):
    """Test multi-session wait with mix of aliased and non-aliased sessions."""
    # Session with alias
    session0 = Session(
        id="0",
        task="Named task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="named",
    )
    save_session(session0)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Named result")

    # Session without alias
    session1 = Session(
        id="1",
        task="Unnamed task",
        parent="",
        state="done",
        tmux_session="scope-1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session1)
    (mock_scope_base / "sessions" / "1" / "result").write_text("Unnamed result")

    result = runner.invoke(main, ["wait", "0", "1"])

    assert result.exit_code == 0
    # Aliased session shows [alias (id)]
    assert "[named (0)]" in result.output
    assert "Named result" in result.output
    # Non-aliased session shows just [id]
    assert "[1]" in result.output
    assert "Unnamed result" in result.output


def test_wait_already_failed(runner, mock_scope_base):
    """Test wait returns exit code 3 if session already failed."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="failed",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["wait", "0"])

    assert result.exit_code == 3


def test_wait_failed_with_reason(runner, mock_scope_base):
    """Test wait outputs failure reason when available."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="failed",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    save_failed_reason("0", "dependency research failed")

    result = runner.invoke(main, ["wait", "0"])

    assert result.exit_code == 3
    assert "Failed: dependency research failed" in result.output


def test_wait_multiple_one_failed(runner, mock_scope_base):
    """Test wait exits 3 if any session failed."""
    session0 = Session(
        id="0",
        task="Task 0",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session0)

    session1 = Session(
        id="1",
        task="Task 1",
        parent="",
        state="failed",
        tmux_session="scope-1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session1)

    result = runner.invoke(main, ["wait", "0", "1"])

    assert result.exit_code == 3


def test_wait_failed_takes_priority_over_aborted(runner, mock_scope_base):
    """Test failed exit code (3) takes priority over aborted (2)."""
    session0 = Session(
        id="0",
        task="Task 0",
        parent="",
        state="aborted",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session0)

    session1 = Session(
        id="1",
        task="Task 1",
        parent="",
        state="failed",
        tmux_session="scope-1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session1)

    result = runner.invoke(main, ["wait", "0", "1"])

    # Failed takes priority over aborted
    assert result.exit_code == 3


def test_wait_multiple_failed_with_reasons(runner, mock_scope_base):
    """Test multi-session wait shows failure reasons with headers."""
    session0 = Session(
        id="0",
        task="Task 0",
        parent="",
        state="failed",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="research",
    )
    save_session(session0)
    save_failed_reason("0", "timeout")

    session1 = Session(
        id="1",
        task="Task 1",
        parent="",
        state="failed",
        tmux_session="scope-1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session1)
    save_failed_reason("1", "dependency failed")

    result = runner.invoke(main, ["wait", "0", "1"])

    assert result.exit_code == 3
    assert "[research (0)]" in result.output
    assert "Failed: timeout" in result.output
    assert "[1]" in result.output
    assert "Failed: dependency failed" in result.output
