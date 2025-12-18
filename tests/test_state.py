"""Tests for state management."""

from datetime import datetime, timezone

from scope.core.session import Session
from scope.core.state import ensure_scope_dir, load_all, load_session, next_id, save_session


def test_ensure_scope_dir(tmp_path, monkeypatch):
    """Test ensure_scope_dir creates directory structure."""
    monkeypatch.chdir(tmp_path)

    scope_dir = ensure_scope_dir()

    assert scope_dir.exists()
    assert (scope_dir / "sessions").exists()
    assert scope_dir == tmp_path / ".scope"


def test_ensure_scope_dir_idempotent(tmp_path, monkeypatch):
    """Test ensure_scope_dir can be called multiple times."""
    monkeypatch.chdir(tmp_path)

    scope_dir1 = ensure_scope_dir()
    scope_dir2 = ensure_scope_dir()

    assert scope_dir1 == scope_dir2
    assert scope_dir1.exists()


def test_next_id_root_sessions(tmp_path, monkeypatch):
    """Test next_id generates sequential root IDs."""
    monkeypatch.chdir(tmp_path)

    assert next_id() == "0"
    assert next_id() == "1"
    assert next_id() == "2"


def test_next_id_persists(tmp_path, monkeypatch):
    """Test next_id counter is persisted to disk."""
    monkeypatch.chdir(tmp_path)

    next_id()  # "0"
    next_id()  # "1"

    # Verify counter file
    counter_file = tmp_path / ".scope" / "next_id"
    assert counter_file.exists()
    assert counter_file.read_text().strip() == "2"


def test_next_id_child_sessions(tmp_path, monkeypatch):
    """Test next_id generates child IDs under parent."""
    monkeypatch.chdir(tmp_path)

    # Create parent session directory
    scope_dir = ensure_scope_dir()
    (scope_dir / "sessions" / "0").mkdir(parents=True)

    assert next_id("0") == "0.0"

    # Create child directory to simulate existing child
    (scope_dir / "sessions" / "0.0").mkdir()
    assert next_id("0") == "0.1"


def test_next_id_nested_children(tmp_path, monkeypatch):
    """Test next_id handles deeply nested children."""
    monkeypatch.chdir(tmp_path)

    scope_dir = ensure_scope_dir()
    (scope_dir / "sessions" / "0").mkdir(parents=True)
    (scope_dir / "sessions" / "0.0").mkdir()

    # Child of 0.0 should be 0.0.0
    assert next_id("0.0") == "0.0.0"


def test_save_session(tmp_path, monkeypatch):
    """Test save_session writes all files correctly."""
    monkeypatch.chdir(tmp_path)

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

    session_dir = tmp_path / ".scope" / "sessions" / "0"
    assert session_dir.exists()
    assert (session_dir / "task").read_text() == "Test task"
    assert (session_dir / "state").read_text() == "running"
    assert (session_dir / "parent").read_text() == ""
    assert (session_dir / "tmux").read_text() == "scope-0"
    assert (session_dir / "created_at").read_text() == created.isoformat()


def test_save_session_with_parent(tmp_path, monkeypatch):
    """Test save_session with parent ID."""
    monkeypatch.chdir(tmp_path)

    session = Session(
        id="0.1",
        task="Child task",
        parent="0",
        state="running",
        tmux_session="scope-0.1",
        created_at=datetime.now(timezone.utc),
    )

    save_session(session)

    session_dir = tmp_path / ".scope" / "sessions" / "0.1"
    assert (session_dir / "parent").read_text() == "0"


def test_load_session(tmp_path, monkeypatch):
    """Test load_session reads session from disk."""
    monkeypatch.chdir(tmp_path)

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


def test_load_session_not_found(tmp_path, monkeypatch):
    """Test load_session returns None for non-existent session."""
    monkeypatch.chdir(tmp_path)

    loaded = load_session("999")

    assert loaded is None


def test_load_session_with_parent(tmp_path, monkeypatch):
    """Test load_session correctly loads parent field."""
    monkeypatch.chdir(tmp_path)

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


def test_load_all_empty(tmp_path, monkeypatch):
    """Test load_all returns empty list when no sessions exist."""
    monkeypatch.chdir(tmp_path)

    sessions = load_all()

    assert sessions == []


def test_load_all_no_scope_dir(tmp_path, monkeypatch):
    """Test load_all returns empty list when .scope doesn't exist."""
    monkeypatch.chdir(tmp_path)

    # Don't create .scope directory
    sessions = load_all()

    assert sessions == []


def test_load_all_single_session(tmp_path, monkeypatch):
    """Test load_all loads a single session."""
    monkeypatch.chdir(tmp_path)

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


def test_load_all_multiple_sessions(tmp_path, monkeypatch):
    """Test load_all loads multiple sessions."""
    monkeypatch.chdir(tmp_path)

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


def test_load_all_sorted_by_created_at(tmp_path, monkeypatch):
    """Test load_all returns sessions sorted by created_at."""
    monkeypatch.chdir(tmp_path)

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


def test_load_all_with_child_sessions(tmp_path, monkeypatch):
    """Test load_all includes child sessions."""
    monkeypatch.chdir(tmp_path)

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
