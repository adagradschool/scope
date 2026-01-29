"""Tests for --pipe flag on spawn command."""

from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.commands.spawn import (
    _collect_piped_results,
    _wait_for_sessions,
)
from scope.core.session import Session
from scope.core.state import ensure_scope_dir, save_session, update_state


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def _init_next_id(mock_scope_base, value: int) -> None:
    """Initialize the next_id counter so spawned sessions get predictable IDs."""
    (mock_scope_base / "next_id").write_text(str(value))


# --- Unit tests for helper functions ---


def test_collect_piped_results_single(mock_scope_base):
    """Test collecting result from a single completed session."""
    session = Session(
        id="0",
        task="Research task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Found 3 libraries.")

    results = _collect_piped_results(["0"])

    assert len(results) == 1
    assert "The previous session [0] produced:" in results[0]
    assert "Found 3 libraries." in results[0]


def test_collect_piped_results_with_alias(mock_scope_base):
    """Test result attribution includes alias when available."""
    session = Session(
        id="0",
        task="Research task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="research",
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Found 3 libraries.")

    results = _collect_piped_results(["0"])

    assert len(results) == 1
    assert "The previous session [research (0)] produced:" in results[0]
    assert "Found 3 libraries." in results[0]


def test_collect_piped_results_multiple(mock_scope_base):
    """Test collecting results from multiple sessions."""
    for i, (alias, text) in enumerate(
        [("research", "Found jwt library."), ("audit", "No vulnerabilities.")]
    ):
        session = Session(
            id=str(i),
            task=f"Task {i}",
            parent="",
            state="done",
            tmux_session=f"scope-{i}",
            created_at=datetime.now(timezone.utc),
            alias=alias,
        )
        save_session(session)
        (mock_scope_base / "sessions" / str(i) / "result").write_text(text)

    results = _collect_piped_results(["0", "1"])

    assert len(results) == 2
    assert "research (0)" in results[0]
    assert "Found jwt library." in results[0]
    assert "audit (1)" in results[1]
    assert "No vulnerabilities." in results[1]


def test_collect_piped_results_no_result_file(mock_scope_base):
    """Test session without result file is skipped."""
    session = Session(
        id="0",
        task="Aborted task",
        parent="",
        state="aborted",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    # No result file written

    results = _collect_piped_results(["0"])

    assert len(results) == 0


def test_collect_piped_results_empty_result(mock_scope_base):
    """Test session with empty result file is skipped."""
    session = Session(
        id="0",
        task="Empty result",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "result").write_text("")

    results = _collect_piped_results(["0"])

    assert len(results) == 0


def test_wait_for_sessions_already_done(mock_scope_base):
    """Test _wait_for_sessions returns immediately for completed sessions."""
    session = Session(
        id="0",
        task="Done task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Should return immediately without blocking
    _wait_for_sessions(["0"])


def test_wait_for_sessions_blocks_until_done(mock_scope_base):
    """Test _wait_for_sessions blocks until session completes."""
    import threading
    import time

    session = Session(
        id="0",
        task="Running task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    def complete_later():
        time.sleep(0.3)
        update_state("0", "done")

    thread = threading.Thread(target=complete_later)
    thread.start()

    _wait_for_sessions(["0"])
    thread.join()

    # If we got here, the wait completed after the state change


# --- Integration tests for spawn --pipe ---


def test_spawn_pipe_help(runner):
    """Test --pipe appears in spawn help."""
    result = runner.invoke(main, ["spawn", "--help"])
    assert result.exit_code == 0
    assert "--pipe" in result.output


def test_spawn_pipe_not_found(runner, mock_scope_base):
    """Test --pipe with non-existent session shows error."""
    result = runner.invoke(main, ["spawn", "--pipe", "999", "Do work"])

    assert result.exit_code == 1
    assert "piped session '999' not found" in result.output


def test_spawn_pipe_done_session(runner, mock_scope_base, cleanup_scope_windows):
    """Test --pipe with already-completed session injects results into contract."""
    # Create a completed parent session with result
    parent = Session(
        id="0",
        task="Research task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="research",
    )
    save_session(parent)
    _init_next_id(mock_scope_base, 1)  # Next spawn gets ID "1"
    (mock_scope_base / "sessions" / "0" / "result").write_text(
        "Found 3 auth libraries: jwt, oauth2, sessions."
    )

    result = runner.invoke(main, ["spawn", "--pipe", "0", "Use the research results"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    # Verify the contract contains piped results
    contract = (mock_scope_base / "sessions" / session_id / "contract.md").read_text()
    assert "# Prior Results" in contract
    assert "The previous session [research (0)] produced:" in contract
    assert "Found 3 auth libraries" in contract
    assert "# Task" in contract
    assert "Use the research results" in contract

    # Verify --pipe implies --after (depends_on includes piped session)
    assert "# Dependencies" in contract
    assert "scope wait 0" in contract


def test_spawn_pipe_multiple_sessions(runner, mock_scope_base, cleanup_scope_windows):
    """Test --pipe with multiple comma-separated session IDs."""
    # Create two completed sessions with results
    for i, (alias, text) in enumerate(
        [("research", "Found jwt library."), ("audit", "No vulnerabilities found.")]
    ):
        session = Session(
            id=str(i),
            task=f"Task {i}",
            parent="",
            state="done",
            tmux_session=f"scope-{i}",
            created_at=datetime.now(timezone.utc),
            alias=alias,
        )
        save_session(session)
        (mock_scope_base / "sessions" / str(i) / "result").write_text(text)
    _init_next_id(mock_scope_base, 2)  # Next spawn gets ID "2"

    result = runner.invoke(
        main, ["spawn", "--pipe", "0,1", "Combine the findings"]
    )

    assert result.exit_code == 0
    session_id = result.output.strip()

    contract = (mock_scope_base / "sessions" / session_id / "contract.md").read_text()
    assert "# Prior Results" in contract
    assert "research (0)" in contract
    assert "Found jwt library." in contract
    assert "audit (1)" in contract
    assert "No vulnerabilities found." in contract


def test_spawn_pipe_implies_after(runner, mock_scope_base, cleanup_scope_windows):
    """Test --pipe adds piped session IDs to depends_on."""
    session = Session(
        id="0",
        task="Parent task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    _init_next_id(mock_scope_base, 1)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Parent result")

    result = runner.invoke(main, ["spawn", "--pipe", "0", "Child task"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    # Check depends_on file was written
    depends_on = (
        (mock_scope_base / "sessions" / session_id / "depends_on").read_text().strip()
    )
    assert "0" in depends_on


def test_spawn_pipe_with_after(runner, mock_scope_base, cleanup_scope_windows):
    """Test --pipe works alongside --after without duplicating deps."""
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
    _init_next_id(mock_scope_base, 2)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Result from 0")

    # --after 0 and --pipe 0 should not duplicate 0 in depends_on
    # --after 1 adds 1 as additional dependency
    result = runner.invoke(
        main, ["spawn", "--after", "0,1", "--pipe", "0", "Do work"]
    )

    assert result.exit_code == 0
    session_id = result.output.strip()

    depends_on = (
        (mock_scope_base / "sessions" / session_id / "depends_on").read_text().strip()
    )
    deps = depends_on.split(",")
    assert "0" in deps
    assert "1" in deps
    # No duplicates
    assert len(deps) == 2


def test_spawn_pipe_no_result_still_spawns(runner, mock_scope_base, cleanup_scope_windows):
    """Test --pipe with done session that has no result file still spawns."""
    session = Session(
        id="0",
        task="Parent task",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    _init_next_id(mock_scope_base, 1)
    # No result file

    result = runner.invoke(main, ["spawn", "--pipe", "0", "Child task"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    # Contract should NOT have Prior Results section (no results to inject)
    contract = (mock_scope_base / "sessions" / session_id / "contract.md").read_text()
    assert "# Prior Results" not in contract
    # But should still have Dependencies (--pipe implies --after)
    assert "# Dependencies" in contract


def test_spawn_pipe_resolves_alias(runner, mock_scope_base, cleanup_scope_windows):
    """Test --pipe resolves aliases to session IDs."""
    session = Session(
        id="0",
        task="Research",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="research",
    )
    save_session(session)
    _init_next_id(mock_scope_base, 1)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Research done.")

    result = runner.invoke(main, ["spawn", "--pipe", "research", "Use results"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    contract = (mock_scope_base / "sessions" / session_id / "contract.md").read_text()
    assert "# Prior Results" in contract
    assert "Research done." in contract
