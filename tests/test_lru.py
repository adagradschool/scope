"""Tests for LRU cache management."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scope.core.session import Session
from scope.core.state import save_session


@pytest.fixture
def mock_lru_cache(tmp_path, monkeypatch):
    """Mock LRU cache to use tmp_path for isolation."""
    cache_path = tmp_path / "lru_cache.json"
    lock_path = tmp_path / "lru_cache.lock"

    def mock_cache_path():
        return cache_path

    def mock_lock_path():
        return lock_path

    monkeypatch.setattr("scope.core.lru._get_lru_cache_path", mock_cache_path)
    monkeypatch.setattr("scope.core.lru._get_lru_lock_path", mock_lock_path)

    return tmp_path


@pytest.fixture
def mock_scope_and_lru(tmp_path, monkeypatch):
    """Mock both scope base and LRU cache for full isolation."""
    # Mock scope base
    def mock_scope_base():
        return tmp_path / "scope"

    monkeypatch.setattr("scope.core.state.get_global_scope_base", mock_scope_base)
    monkeypatch.delenv("SCOPE_SESSION_ID", raising=False)

    # Mock LRU cache paths
    cache_path = tmp_path / "lru_cache.json"
    lock_path = tmp_path / "lru_cache.lock"

    def mock_cache_path():
        return cache_path

    def mock_lock_path():
        return lock_path

    monkeypatch.setattr("scope.core.lru._get_lru_cache_path", mock_cache_path)
    monkeypatch.setattr("scope.core.lru._get_lru_lock_path", mock_lock_path)

    # Create sessions directory
    (tmp_path / "scope" / "sessions").mkdir(parents=True, exist_ok=True)

    return tmp_path


def test_empty_cache(mock_lru_cache):
    """Test loading empty/nonexistent cache."""
    from scope.core.lru import load_lru_cache

    cache = load_lru_cache()

    assert cache["version"] == 1
    assert cache["entries"] == []


def test_save_and_load_cache(mock_lru_cache):
    """Test saving and loading cache."""
    from scope.core.lru import load_lru_cache, save_lru_cache

    cache = {
        "version": 1,
        "entries": [
            {
                "project_id": "test-abc123",
                "session_id": "0",
                "last_accessed": "2024-01-01T12:00:00",
            }
        ],
    }
    save_lru_cache(cache)

    loaded = load_lru_cache()

    assert loaded["version"] == 1
    assert len(loaded["entries"]) == 1
    assert loaded["entries"][0]["project_id"] == "test-abc123"
    assert loaded["entries"][0]["session_id"] == "0"


def test_add_completed_session(mock_lru_cache):
    """Test adding a completed session to the cache."""
    from scope.core.lru import add_completed_session, load_lru_cache

    add_completed_session("project-abc", "0")

    cache = load_lru_cache()
    assert len(cache["entries"]) == 1
    assert cache["entries"][0]["project_id"] == "project-abc"
    assert cache["entries"][0]["session_id"] == "0"
    assert "last_accessed" in cache["entries"][0]


def test_add_completed_session_updates_existing(mock_lru_cache):
    """Test adding an existing session updates its last_accessed."""
    from scope.core.lru import add_completed_session, load_lru_cache

    add_completed_session("project-abc", "0")
    cache1 = load_lru_cache()
    first_access = cache1["entries"][0]["last_accessed"]

    # Add same session again
    import time

    time.sleep(0.01)  # Ensure different timestamp
    add_completed_session("project-abc", "0")

    cache2 = load_lru_cache()
    assert len(cache2["entries"]) == 1
    assert cache2["entries"][0]["last_accessed"] >= first_access


def test_touch_session(mock_lru_cache):
    """Test touching a session updates last_accessed."""
    from scope.core.lru import add_completed_session, load_lru_cache, touch_session

    add_completed_session("project-abc", "0")
    cache1 = load_lru_cache()
    first_access = cache1["entries"][0]["last_accessed"]

    import time

    time.sleep(0.01)
    touch_session("project-abc", "0")

    cache2 = load_lru_cache()
    assert cache2["entries"][0]["last_accessed"] >= first_access


def test_touch_nonexistent_session(mock_lru_cache):
    """Test touching nonexistent session is a no-op."""
    from scope.core.lru import load_lru_cache, touch_session

    touch_session("project-abc", "999")

    cache = load_lru_cache()
    assert len(cache["entries"]) == 0


def test_remove_session(mock_lru_cache):
    """Test removing a session from cache."""
    from scope.core.lru import add_completed_session, load_lru_cache, remove_session

    add_completed_session("project-abc", "0")
    add_completed_session("project-abc", "1")

    remove_session("project-abc", "0")

    cache = load_lru_cache()
    assert len(cache["entries"]) == 1
    assert cache["entries"][0]["session_id"] == "1"


def test_remove_nonexistent_session(mock_lru_cache):
    """Test removing nonexistent session is a no-op."""
    from scope.core.lru import add_completed_session, load_lru_cache, remove_session

    add_completed_session("project-abc", "0")

    remove_session("project-abc", "999")

    cache = load_lru_cache()
    assert len(cache["entries"]) == 1


def test_get_completed_count(mock_lru_cache):
    """Test getting completed session count."""
    from scope.core.lru import add_completed_session, get_completed_count

    assert get_completed_count() == 0

    add_completed_session("project-abc", "0")
    assert get_completed_count() == 1

    add_completed_session("project-abc", "1")
    assert get_completed_count() == 2


def test_check_and_evict_under_limit(mock_lru_cache, monkeypatch):
    """Test check_and_evict does nothing when under limit."""
    from scope.core.lru import add_completed_session, check_and_evict, load_lru_cache

    monkeypatch.setattr("scope.core.lru.get_max_completed_sessions", lambda: 5)

    add_completed_session("project-abc", "0")
    add_completed_session("project-abc", "1")

    evicted = check_and_evict()

    assert evicted == []
    cache = load_lru_cache()
    assert len(cache["entries"]) == 2


def test_check_and_evict_at_limit(mock_lru_cache, monkeypatch):
    """Test check_and_evict does nothing when at limit."""
    from scope.core.lru import add_completed_session, check_and_evict, load_lru_cache

    monkeypatch.setattr("scope.core.lru.get_max_completed_sessions", lambda: 2)

    add_completed_session("project-abc", "0")
    add_completed_session("project-abc", "1")

    evicted = check_and_evict()

    assert evicted == []
    cache = load_lru_cache()
    assert len(cache["entries"]) == 2


def test_check_and_evict_over_limit(mock_scope_and_lru, monkeypatch):
    """Test check_and_evict evicts oldest when over limit."""
    from scope.core.lru import add_completed_session, check_and_evict, load_lru_cache

    # Mock tmux functions to avoid actual tmux calls
    monkeypatch.setattr("scope.core.lru.has_window_in_session", lambda s, w: False)
    monkeypatch.setattr("scope.core.lru.get_max_completed_sessions", lambda: 2)

    # Create session directories so eviction can update state
    scope_dir = mock_scope_and_lru / "scope"
    repos_dir = Path.home() / ".scope" / "repos"

    # Add sessions with different timestamps
    import time

    add_completed_session("project-abc", "0")
    time.sleep(0.01)
    add_completed_session("project-abc", "1")
    time.sleep(0.01)
    add_completed_session("project-abc", "2")

    # Should evict session 0 (oldest)
    evicted = check_and_evict()

    assert len(evicted) == 1
    assert evicted[0] == ("project-abc", "0")

    cache = load_lru_cache()
    assert len(cache["entries"]) == 2
    session_ids = [e["session_id"] for e in cache["entries"]]
    assert "0" not in session_ids
    assert "1" in session_ids
    assert "2" in session_ids


def test_check_and_evict_with_override_limit(mock_lru_cache, monkeypatch):
    """Test check_and_evict respects override limit."""
    from scope.core.lru import add_completed_session, check_and_evict, load_lru_cache

    monkeypatch.setattr("scope.core.lru.has_window_in_session", lambda s, w: False)
    monkeypatch.setattr("scope.core.lru.get_max_completed_sessions", lambda: 10)

    add_completed_session("project-abc", "0")
    add_completed_session("project-abc", "1")
    add_completed_session("project-abc", "2")

    # Override to 1
    evicted = check_and_evict(max_completed=1)

    assert len(evicted) == 2
    cache = load_lru_cache()
    assert len(cache["entries"]) == 1


def test_evict_session_updates_state(mock_scope_and_lru, monkeypatch):
    """Test evict_session updates session state to evicted."""
    from scope.core.lru import evict_session

    # Mock tmux functions
    monkeypatch.setattr("scope.core.lru.has_window_in_session", lambda s, w: False)

    # Create a session directory with state file
    project_id = "test-project"
    session_id = "0"
    repos_dir = Path.home() / ".scope" / "repos"
    session_dir = repos_dir / project_id / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "state").write_text("done")

    evict_session(project_id, session_id)

    assert (session_dir / "state").read_text() == "evicted"


def test_evict_session_kills_tmux_window(mock_scope_and_lru, monkeypatch):
    """Test evict_session attempts to kill tmux window."""
    from scope.core.lru import evict_session

    killed_windows = []

    def mock_kill(session, window):
        killed_windows.append((session, window))

    monkeypatch.setattr("scope.core.lru.has_window_in_session", lambda s, w: True)
    monkeypatch.setattr("scope.core.lru.kill_window_in_session", mock_kill)

    project_id = "test-project"
    session_id = "0"

    result = evict_session(project_id, session_id)

    assert result is True
    assert len(killed_windows) == 1
    assert killed_windows[0] == (f"scope-{project_id}", "w0")


class TestConfig:
    """Tests for max_completed_sessions config."""

    def test_get_default(self, tmp_path, monkeypatch):
        """Test get_max_completed_sessions returns default."""
        from scope.core.config import get_max_completed_sessions

        config_path = tmp_path / "config.json"
        monkeypatch.setattr(
            "scope.core.config.get_scope_config_path", lambda: config_path
        )

        result = get_max_completed_sessions()

        assert result == 5

    def test_get_configured(self, tmp_path, monkeypatch):
        """Test get_max_completed_sessions returns configured value."""
        import orjson

        from scope.core.config import get_max_completed_sessions

        config_path = tmp_path / "config.json"
        config_path.write_bytes(orjson.dumps({"max_completed_sessions": 10}))
        monkeypatch.setattr(
            "scope.core.config.get_scope_config_path", lambda: config_path
        )

        result = get_max_completed_sessions()

        assert result == 10

    def test_set_config(self, tmp_path, monkeypatch):
        """Test set_max_completed_sessions writes config."""
        import orjson

        from scope.core.config import get_max_completed_sessions, set_max_completed_sessions

        config_path = tmp_path / "config.json"
        monkeypatch.setattr(
            "scope.core.config.get_scope_config_path", lambda: config_path
        )

        set_max_completed_sessions(3)

        assert get_max_completed_sessions() == 3

    def test_set_negative_raises(self, tmp_path, monkeypatch):
        """Test set_max_completed_sessions raises for negative value."""
        from scope.core.config import set_max_completed_sessions

        config_path = tmp_path / "config.json"
        monkeypatch.setattr(
            "scope.core.config.get_scope_config_path", lambda: config_path
        )

        with pytest.raises(ValueError, match="must be >= 0"):
            set_max_completed_sessions(-1)


class TestClaudeSessionId:
    """Tests for Claude session ID helpers."""

    def test_save_and_load(self, mock_scope_base):
        """Test saving and loading Claude session ID."""
        from scope.core.state import (
            load_claude_session_id,
            save_claude_session_id,
            save_session,
        )

        # Create a session first
        session = Session(
            id="0",
            task="Test",
            parent="",
            state="done",
            tmux_session="w0",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

        # Save and load Claude session ID
        claude_uuid = "04cad4c6-1aee-4ac7-b38c-596edda8e3e5"
        save_claude_session_id("0", claude_uuid)

        loaded = load_claude_session_id("0")

        assert loaded == claude_uuid

    def test_load_nonexistent(self, mock_scope_base):
        """Test loading nonexistent Claude session ID."""
        from scope.core.state import load_claude_session_id, save_session

        # Create a session without Claude ID
        session = Session(
            id="0",
            task="Test",
            parent="",
            state="done",
            tmux_session="w0",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

        loaded = load_claude_session_id("0")

        assert loaded is None

    def test_save_to_nonexistent_session_raises(self, mock_scope_base):
        """Test saving to nonexistent session raises."""
        from scope.core.state import save_claude_session_id

        with pytest.raises(FileNotFoundError):
            save_claude_session_id("999", "some-uuid")


class TestExtractClaudeSessionId:
    """Tests for extracting Claude session ID from transcript."""

    def test_extract_from_transcript(self, tmp_path):
        """Test extracting session ID from transcript."""
        import orjson

        from scope.hooks.handler import extract_claude_session_id

        transcript = tmp_path / "test.jsonl"
        entries = [
            {"type": "system", "sessionId": "04cad4c6-1aee-4ac7-b38c-596edda8e3e5"},
            {"type": "user", "message": {"content": "Hello"}},
        ]
        with transcript.open("w") as f:
            for entry in entries:
                f.write(orjson.dumps(entry).decode() + "\n")

        result = extract_claude_session_id(str(transcript))

        assert result == "04cad4c6-1aee-4ac7-b38c-596edda8e3e5"

    def test_extract_no_session_id(self, tmp_path):
        """Test extracting from transcript without session ID."""
        import orjson

        from scope.hooks.handler import extract_claude_session_id

        transcript = tmp_path / "test.jsonl"
        entries = [
            {"type": "user", "message": {"content": "Hello"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}},
        ]
        with transcript.open("w") as f:
            for entry in entries:
                f.write(orjson.dumps(entry).decode() + "\n")

        result = extract_claude_session_id(str(transcript))

        assert result is None

    def test_extract_nonexistent_file(self):
        """Test extracting from nonexistent file."""
        from scope.hooks.handler import extract_claude_session_id

        result = extract_claude_session_id("/nonexistent/path.jsonl")

        assert result is None


class TestSessionEvictedState:
    """Tests for evicted session state."""

    def test_evicted_is_valid_state(self):
        """Test that evicted is a valid session state."""
        from scope.core.session import VALID_STATES

        assert "evicted" in VALID_STATES

    def test_session_with_evicted_state(self):
        """Test creating session with evicted state."""
        session = Session(
            id="0",
            task="Test",
            parent="",
            state="evicted",
            tmux_session="w0",
            created_at=datetime.now(timezone.utc),
        )

        assert session.state == "evicted"

    def test_save_and_load_evicted_session(self, mock_scope_base):
        """Test saving and loading evicted session."""
        from scope.core.state import load_session

        session = Session(
            id="0",
            task="Test",
            parent="",
            state="evicted",
            tmux_session="w0",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

        loaded = load_session("0")

        assert loaded is not None
        assert loaded.state == "evicted"


def _add_session_concurrent(args: tuple) -> str:
    """Helper for concurrent test - adds a session to LRU cache.

    This is a module-level function so it can be pickled for ProcessPoolExecutor.
    """
    import scope.core.lru as lru_module

    cache_path_str, lock_path_str, project_id, session_id = args
    cache_path = Path(cache_path_str)
    lock_path = Path(lock_path_str)

    # Patch the path functions
    lru_module._get_lru_cache_path = lambda: cache_path
    lru_module._get_lru_lock_path = lambda: lock_path

    lru_module.add_completed_session(project_id, session_id)
    return session_id


def test_lru_concurrent_adds(tmp_path):
    """Test that concurrent add_completed_session calls work correctly.

    This verifies the file locking works to prevent race conditions.
    """
    from concurrent.futures import ProcessPoolExecutor

    from scope.core.lru import _get_lru_cache_path, _get_lru_lock_path, load_lru_cache

    cache_path = tmp_path / "lru_cache.json"
    lock_path = tmp_path / "lru_cache.lock"

    num_workers = 5
    calls_per_worker = 3
    total_calls = num_workers * calls_per_worker

    # Prepare arguments for concurrent calls
    args_list = [
        (str(cache_path), str(lock_path), "project-abc", str(i))
        for i in range(total_calls)
    ]

    # Run concurrent add_completed_session calls
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = list(executor.map(_add_session_concurrent, args_list))

    # Verify all sessions were added
    assert len(results) == total_calls

    # Load cache and verify all entries are present
    import scope.core.lru as lru_module

    lru_module._get_lru_cache_path = lambda: cache_path
    lru_module._get_lru_lock_path = lambda: lock_path

    cache = load_lru_cache()
    entries = cache.get("entries", [])

    assert len(entries) == total_calls
    session_ids = {e["session_id"] for e in entries}
    expected_ids = {str(i) for i in range(total_calls)}
    assert session_ids == expected_ids
