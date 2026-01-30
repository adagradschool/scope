"""Tests for state management."""

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from scope.core.session import Session
from scope.core.state import (
    ensure_scope_dir,
    load_all,
    load_loop_state,
    load_session,
    next_id,
    save_loop_state,
    save_session,
)


def _call_next_id_with_scope_dir(scope_dir_str: str) -> str:
    """Helper for concurrent test - calls next_id() with a specific scope dir.

    This is a module-level function so it can be pickled for ProcessPoolExecutor.
    """
    import scope.core.state as state_module

    scope_dir = Path(scope_dir_str)

    # Patch get_global_scope_base to return the test directory
    original_fn = state_module.get_global_scope_base
    state_module.get_global_scope_base = lambda: scope_dir

    try:
        return next_id()
    finally:
        state_module.get_global_scope_base = original_fn


def test_ensure_scope_dir(mock_scope_base):
    """Test ensure_scope_dir creates directory structure."""
    scope_dir = ensure_scope_dir()

    assert scope_dir.exists()
    assert (scope_dir / "sessions").exists()
    assert scope_dir == mock_scope_base


def test_ensure_scope_dir_idempotent(mock_scope_base):
    """Test ensure_scope_dir can be called multiple times."""
    scope_dir1 = ensure_scope_dir()
    scope_dir2 = ensure_scope_dir()

    assert scope_dir1 == scope_dir2
    assert scope_dir1.exists()


def test_next_id_root_sessions(mock_scope_base):
    """Test next_id generates sequential root IDs."""
    assert next_id() == "0"
    assert next_id() == "1"
    assert next_id() == "2"


def test_next_id_persists(mock_scope_base):
    """Test next_id counter is persisted to disk."""
    next_id()  # "0"
    next_id()  # "1"

    # Verify counter file
    counter_file = mock_scope_base / "next_id"
    assert counter_file.exists()
    assert counter_file.read_text().strip() == "2"


def test_next_id_child_sessions(mock_scope_base):
    """Test next_id generates child IDs under parent."""
    # Create parent session directory
    scope_dir = ensure_scope_dir()
    (scope_dir / "sessions" / "0").mkdir(parents=True)

    assert next_id("0") == "0.0"

    # Create child directory to simulate existing child
    (scope_dir / "sessions" / "0.0").mkdir()
    assert next_id("0") == "0.1"


def test_next_id_nested_children(mock_scope_base):
    """Test next_id handles deeply nested children."""
    scope_dir = ensure_scope_dir()
    (scope_dir / "sessions" / "0").mkdir(parents=True)
    (scope_dir / "sessions" / "0.0").mkdir()

    # Child of 0.0 should be 0.0.0
    assert next_id("0.0") == "0.0.0"


def test_save_session(mock_scope_base):
    """Test save_session writes all files correctly."""
    created = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=created,
    )

    save_session(session)

    session_dir = mock_scope_base / "sessions" / "0"
    assert session_dir.exists()
    assert (session_dir / "task").read_text() == "Test task"
    assert (session_dir / "state").read_text() == "running"
    assert (session_dir / "parent").read_text() == ""
    assert (session_dir / "tmux").read_text() == "scope-0"
    assert (session_dir / "created_at").read_text() == created.isoformat()


def test_save_session_with_parent(mock_scope_base):
    """Test save_session with parent ID."""
    session = Session(
        id="0.1",
        task="Child task",
        parent="0",
        state="running",
        tmux_session="scope-0.1",
        created_at=datetime.now(timezone.utc),
    )

    save_session(session)

    session_dir = mock_scope_base / "sessions" / "0.1"
    assert (session_dir / "parent").read_text() == "0"


def test_load_session(mock_scope_base):
    """Test load_session reads session from disk."""
    created = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=created,
    )
    save_session(session)

    loaded = load_session("0")

    assert loaded is not None
    assert loaded.id == "0"
    assert loaded.task == "Test task"
    assert loaded.parent == ""
    assert loaded.state == "running"
    assert loaded.tmux_session == "scope-0"
    assert loaded.created_at == created


def test_load_session_not_found(mock_scope_base):
    """Test load_session returns None for non-existent session."""
    loaded = load_session("999")

    assert loaded is None


def test_load_session_with_parent(mock_scope_base):
    """Test load_session correctly loads parent field."""
    session = Session(
        id="0.1",
        task="Child task",
        parent="0",
        state="running",
        tmux_session="scope-0.1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    loaded = load_session("0.1")

    assert loaded is not None
    assert loaded.parent == "0"


def test_load_all_empty(mock_scope_base):
    """Test load_all returns empty list when no sessions exist."""
    sessions = load_all()

    assert sessions == []


def test_load_all_no_scope_dir(mock_scope_base):
    """Test load_all returns empty list when scope dir doesn't exist."""
    # Don't create sessions directory
    sessions = load_all()

    assert sessions == []


def test_load_all_single_session(mock_scope_base):
    """Test load_all loads a single session."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    sessions = load_all()

    assert len(sessions) == 1
    assert sessions[0].id == "0"
    assert sessions[0].task == "Test task"


def test_load_all_multiple_sessions(mock_scope_base):
    """Test load_all loads multiple sessions."""
    # Create sessions with different timestamps
    session0 = Session(
        id="0",
        task="First task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    session1 = Session(
        id="1",
        task="Second task",
        parent="",
        state="done",
        tmux_session="scope-1",
        created_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    save_session(session0)
    save_session(session1)

    sessions = load_all()

    assert len(sessions) == 2
    assert sessions[0].id == "0"
    assert sessions[1].id == "1"


def test_load_all_sorted_by_created_at(mock_scope_base):
    """Test load_all returns sessions sorted by created_at."""
    # Create sessions out of order (newer first)
    newer = Session(
        id="0",
        task="Newer task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
    )
    older = Session(
        id="1",
        task="Older task",
        parent="",
        state="running",
        tmux_session="scope-1",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    save_session(newer)
    save_session(older)

    sessions = load_all()

    # Should be sorted oldest first
    assert len(sessions) == 2
    assert sessions[0].id == "1"  # older
    assert sessions[1].id == "0"  # newer


def test_load_all_with_child_sessions(mock_scope_base):
    """Test load_all includes child sessions."""
    parent = Session(
        id="0",
        task="Parent task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    child = Session(
        id="0.0",
        task="Child task",
        parent="0",
        state="running",
        tmux_session="scope-0.0",
        created_at=datetime(2024, 1, 1, 12, 30, 0, tzinfo=timezone.utc),
    )
    save_session(parent)
    save_session(child)

    sessions = load_all()

    assert len(sessions) == 2
    ids = [s.id for s in sessions]
    assert "0" in ids
    assert "0.0" in ids


def test_next_id_concurrent_returns_unique_ids(tmp_path):
    """Test that concurrent next_id() calls return unique IDs.

    This verifies the fcntl.flock() fix for the TOCTOU race condition.
    Uses ProcessPoolExecutor to simulate concurrent processes.
    """
    # Create the sessions directory so ensure_scope_dir doesn't fail
    (tmp_path / "sessions").mkdir(parents=True)

    num_workers = 10
    calls_per_worker = 5
    total_calls = num_workers * calls_per_worker

    # Run concurrent next_id() calls across multiple processes
    scope_dir_str = str(tmp_path)
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(_call_next_id_with_scope_dir, scope_dir_str)
            for _ in range(total_calls)
        ]
        results = [f.result() for f in futures]

    # All IDs should be unique
    assert len(results) == total_calls
    assert len(set(results)) == total_calls, f"Duplicate IDs found: {results}"

    # IDs should be sequential integers 0 through total_calls-1
    expected_ids = {str(i) for i in range(total_calls)}
    assert set(results) == expected_ids


# --- Loop state tests ---


def test_save_and_load_loop_state(mock_scope_base):
    """Test saving and loading loop state."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    save_session(session)

    save_loop_state(
        session_id="0",
        checker="pytest tests/",
        max_iterations=3,
        current_iteration=1,
        history=[
            {"iteration": 0, "doer_session": "0.1", "verdict": "retry", "feedback": "3 tests fail"},
        ],
    )

    state = load_loop_state("0")
    assert state is not None
    assert state["checker"] == "pytest tests/"
    assert state["max_iterations"] == 3
    assert state["current_iteration"] == 1
    assert len(state["history"]) == 1
    assert state["history"][0]["verdict"] == "retry"
    assert state["history"][0]["feedback"] == "3 tests fail"


def test_load_loop_state_nonexistent(mock_scope_base):
    """Test loading loop state for session without loop state."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    save_session(session)

    state = load_loop_state("0")
    assert state is None


def test_load_loop_state_no_session(mock_scope_base):
    """Test loading loop state for nonexistent session."""
    state = load_loop_state("999")
    assert state is None


def test_save_loop_state_overwrites(mock_scope_base):
    """Test saving loop state overwrites previous state."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    save_session(session)

    save_loop_state("0", "pytest", 3, 0, [])
    save_loop_state("0", "pytest", 3, 1, [{"iteration": 0, "verdict": "retry", "feedback": "fail"}])

    state = load_loop_state("0")
    assert state["current_iteration"] == 1
    assert len(state["history"]) == 1
