"""Tests for wait command."""

import threading
import time
from datetime import datetime, timezone
from unittest.mock import patch

import orjson
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


# --- Summary mode tests ---
#
# Summary tests mock _summarize_result since it shells out to claude -p.


def _mock_summarize(task, result_text, status):
    """Deterministic mock for _summarize_result."""
    return f"Summary of {task}"


@pytest.fixture
def mock_summarize():
    """Patch _summarize_result to avoid subprocess calls in tests."""
    with patch(
        "scope.commands.wait._summarize_result", side_effect=_mock_summarize
    ) as m:
        yield m


def test_wait_summary_flag_exists(runner):
    """Test wait --help shows --summary flag."""
    result = runner.invoke(main, ["wait", "--help"])
    assert result.exit_code == 0
    assert "--summary" in result.output


def test_wait_summary_returns_compact_output(runner, mock_scope_base, mock_summarize):
    """Test wait --summary returns LLM-generated summary instead of full result."""
    session = Session(
        id="0",
        task="Fix auth bug",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Write a result file with detailed content
    result_file = mock_scope_base / "sessions" / "0" / "result"
    result_file.write_text(
        "I fixed the authentication bug in src/auth.ts.\n"
        "The issue was that the JWT token was not being validated correctly.\n"
        "All tests pass now.\n"
    )

    # Write trajectory index with tool summary
    index_file = mock_scope_base / "sessions" / "0" / "trajectory_index.json"
    index_data = {
        "turn_count": 8,
        "tool_calls": ["Read", "Grep", "Edit", "Edit", "Write", "Bash"],
        "tool_summary": {"Read": 1, "Grep": 1, "Edit": 2, "Write": 1, "Bash": 1},
    }
    index_file.write_bytes(orjson.dumps(index_data))

    result = runner.invoke(main, ["wait", "--summary", "0"])

    assert result.exit_code == 0
    output = result.output
    # Summary should include pass/fail status
    assert "PASS" in output
    # Summary should include the LLM-generated summary
    assert "Summary of Fix auth bug" in output
    # Summary should include files changed count
    assert "files_changed=3" in output
    # Summary should include test status
    assert "tests=pass" in output
    # Summary should NOT include the full multi-line result
    assert "JWT token" not in output
    # _summarize_result was called with task, result text, and status
    mock_summarize.assert_called_once()


def test_wait_summary_includes_pass_fail(runner, mock_scope_base, mock_summarize):
    """Test summary shows PASS for done sessions and FAIL for failed."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Done.")

    result = runner.invoke(main, ["wait", "--summary", "0"])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_wait_summary_failed_session(runner, mock_scope_base):
    """Test summary shows FAIL for failed sessions."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="failed",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    save_failed_reason("0", "dependency failed")

    result = runner.invoke(main, ["wait", "--summary", "0"])
    assert result.exit_code == 3
    assert "FAIL" in result.output


def test_wait_summary_files_changed(runner, mock_scope_base, mock_summarize):
    """Test summary includes files changed count from trajectory index."""
    session = Session(
        id="0",
        task="Refactor",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Refactored.")

    # Write trajectory index with Edit and Write tool calls
    index_file = mock_scope_base / "sessions" / "0" / "trajectory_index.json"
    index_data = {
        "turn_count": 4,
        "tool_calls": ["Edit", "Edit", "Write"],
        "tool_summary": {"Edit": 2, "Write": 1},
    }
    index_file.write_bytes(orjson.dumps(index_data))

    result = runner.invoke(main, ["wait", "--summary", "0"])
    assert result.exit_code == 0
    assert "files_changed=3" in result.output


def test_wait_summary_test_status_pass(runner, mock_scope_base, mock_summarize):
    """Test summary detects passing tests from result text."""
    session = Session(
        id="0",
        task="Fix bug",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "result").write_text(
        "Fixed the bug. All tests passed."
    )

    index_file = mock_scope_base / "sessions" / "0" / "trajectory_index.json"
    index_data = {
        "turn_count": 3,
        "tool_calls": ["Edit", "Bash"],
        "tool_summary": {"Edit": 1, "Bash": 1},
    }
    index_file.write_bytes(orjson.dumps(index_data))

    result = runner.invoke(main, ["wait", "--summary", "0"])
    assert result.exit_code == 0
    assert "tests=pass" in result.output


def test_wait_summary_test_status_fail(runner, mock_scope_base, mock_summarize):
    """Test summary detects failing tests from result text."""
    session = Session(
        id="0",
        task="Fix bug",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "result").write_text(
        "Attempted fix but 2 tests failed."
    )

    index_file = mock_scope_base / "sessions" / "0" / "trajectory_index.json"
    index_data = {
        "turn_count": 3,
        "tool_calls": ["Edit", "Bash"],
        "tool_summary": {"Edit": 1, "Bash": 1},
    }
    index_file.write_bytes(orjson.dumps(index_data))

    result = runner.invoke(main, ["wait", "--summary", "0"])
    assert result.exit_code == 0
    assert "tests=fail" in result.output


def test_wait_summary_no_tests(runner, mock_scope_base, mock_summarize):
    """Test summary shows tests=none when no Bash calls."""
    session = Session(
        id="0",
        task="Read code",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Reviewed the code.")

    result = runner.invoke(main, ["wait", "--summary", "0"])
    assert result.exit_code == 0
    assert "tests=none" in result.output


def test_wait_regular_still_returns_full_result(runner, mock_scope_base):
    """Test wait without --summary still returns full result text."""
    session = Session(
        id="0",
        task="Fix auth bug",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    full_result = (
        "I fixed the authentication bug in src/auth.ts.\n"
        "The issue was that the JWT token was not being validated correctly.\n"
        "All tests pass now.\n"
    )
    result_file = mock_scope_base / "sessions" / "0" / "result"
    result_file.write_text(full_result)

    result = runner.invoke(main, ["wait", "0"])
    assert result.exit_code == 0
    # Full result should be present without --summary
    assert "JWT token" in result.output
    assert "PASS" not in result.output  # No summary markers


def test_wait_summary_aborted_session(runner, mock_scope_base, mock_summarize):
    """Test summary shows ABORT for aborted sessions."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="aborted",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = runner.invoke(main, ["wait", "--summary", "0"])
    assert result.exit_code == 2
    assert "ABORT" in result.output


def test_wait_summary_multiple_sessions(runner, mock_scope_base, mock_summarize):
    """Test summary works with multiple sessions."""
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
        (mock_scope_base / "sessions" / str(i) / "result").write_text(
            f"Completed task {i}."
        )

    result = runner.invoke(main, ["wait", "--summary", "0", "1", "2"])

    assert result.exit_code == 0
    # Each session should have a header and compact summary
    assert "[0]" in result.output
    assert "[1]" in result.output
    assert "[2]" in result.output
    assert "PASS" in result.output
    assert result.output.count("PASS") == 3
