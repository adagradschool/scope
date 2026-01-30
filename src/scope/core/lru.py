"""LRU cache for managing completed sub-agent sessions.

Keeps running agents active indefinitely, but caps completed agents at a
configurable limit. Evicted sessions have their tmux windows killed but
remain in "done" state with data preserved on disk.

Global LRU cache stored at ~/.scope/lru_cache.json
Schema:
{
  "version": 1,
  "entries": [
    {"project_id": "...", "session_id": "...", "last_accessed": "ISO8601"}
  ]
}
"""

import fcntl
from datetime import datetime
from pathlib import Path

import orjson

from scope.core.config import get_max_completed_sessions
from scope.core.tmux import (
    has_window_in_session,
    kill_window_in_session,
    tmux_window_name,
)

LRU_CACHE_VERSION = 1


def _get_lru_cache_path() -> Path:
    """Get the path to the global LRU cache file."""
    return Path.home() / ".scope" / "lru_cache.json"


def _get_lru_lock_path() -> Path:
    """Get the path to the LRU cache lock file."""
    return Path.home() / ".scope" / "lru_cache.lock"


def _empty_cache() -> dict:
    """Return an empty LRU cache structure."""
    return {"version": LRU_CACHE_VERSION, "entries": []}


def _load_cache_unlocked() -> dict:
    """Load cache without acquiring lock (for use inside locked operations)."""
    cache_path = _get_lru_cache_path()

    try:
        if not cache_path.exists():
            return _empty_cache()
        content = cache_path.read_bytes()
        if not content:
            return _empty_cache()
        cache = orjson.loads(content)
        if cache.get("version") != LRU_CACHE_VERSION:
            return _empty_cache()
        return cache
    except (orjson.JSONDecodeError, OSError):
        return _empty_cache()


def _save_cache_unlocked(cache: dict) -> None:
    """Save cache without acquiring lock (for use inside locked operations)."""
    cache_path = _get_lru_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(orjson.dumps(cache, option=orjson.OPT_INDENT_2))


def load_lru_cache() -> dict:
    """Load the LRU cache from disk with file locking.

    Returns:
        The LRU cache dict. Returns empty cache if file doesn't exist.
    """
    cache_path = _get_lru_cache_path()
    lock_path = _get_lru_lock_path()

    # Ensure parent directory exists
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_SH)
            try:
                return _load_cache_unlocked()
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
    except OSError:
        return _empty_cache()


def save_lru_cache(cache: dict) -> None:
    """Save the LRU cache to disk with file locking.

    Args:
        cache: The LRU cache dict to save.
    """
    lock_path = _get_lru_lock_path()

    # Ensure parent directory exists
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            _save_cache_unlocked(cache)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def touch_session(project_id: str, session_id: str) -> None:
    """Update the last_accessed time for a session in the LRU cache.

    If the session doesn't exist in the cache, this is a no-op.

    Args:
        project_id: The project identifier (e.g., "myrepo-abc12345").
        session_id: The scope session ID (e.g., "0", "0.1").
    """
    lock_path = _get_lru_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            cache = _load_cache_unlocked()
            entries = cache.get("entries", [])

            for entry in entries:
                if (
                    entry["project_id"] == project_id
                    and entry["session_id"] == session_id
                ):
                    entry["last_accessed"] = datetime.now().isoformat()
                    _save_cache_unlocked(cache)
                    return
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def add_completed_session(project_id: str, session_id: str) -> None:
    """Add a completed session to the LRU cache.

    If the session already exists, updates its last_accessed time.

    Args:
        project_id: The project identifier (e.g., "myrepo-abc12345").
        session_id: The scope session ID (e.g., "0", "0.1").
    """
    lock_path = _get_lru_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            cache = _load_cache_unlocked()
            entries = cache.get("entries", [])

            # Check if already exists
            for entry in entries:
                if (
                    entry["project_id"] == project_id
                    and entry["session_id"] == session_id
                ):
                    entry["last_accessed"] = datetime.now().isoformat()
                    _save_cache_unlocked(cache)
                    return

            # Add new entry
            entries.append(
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "last_accessed": datetime.now().isoformat(),
                }
            )
            cache["entries"] = entries
            _save_cache_unlocked(cache)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def remove_session(project_id: str, session_id: str) -> None:
    """Remove a session from the LRU cache.

    Args:
        project_id: The project identifier (e.g., "myrepo-abc12345").
        session_id: The scope session ID (e.g., "0", "0.1").
    """
    lock_path = _get_lru_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            cache = _load_cache_unlocked()
            entries = cache.get("entries", [])

            cache["entries"] = [
                e
                for e in entries
                if not (e["project_id"] == project_id and e["session_id"] == session_id)
            ]
            _save_cache_unlocked(cache)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def evict_session(project_id: str, session_id: str) -> bool:
    """Evict a session by killing its tmux window.

    The session state remains "done" on disk; only the tmux window is killed
    and the entry is removed from the LRU cache.

    Args:
        project_id: The project identifier (e.g., "myrepo-abc12345").
        session_id: The scope session ID (e.g., "0", "0.1").

    Returns:
        True if the tmux window was killed, False if it didn't exist.
    """

    # Kill tmux window if it exists
    # We need to figure out which tmux session this belongs to
    # The tmux session name is "scope-{project_id}"
    tmux_session = f"scope-{project_id}"
    window_name = tmux_window_name(session_id)

    window_killed = False
    if has_window_in_session(tmux_session, window_name):
        try:
            kill_window_in_session(tmux_session, window_name)
            window_killed = True
        except Exception:
            pass  # Window may have already been killed

    # Remove from LRU cache (session stays "done" on disk)
    remove_session(project_id, session_id)

    return window_killed


def check_and_evict(max_completed: int | None = None) -> list[tuple[str, str]]:
    """Check if we're over the completed sessions limit and evict oldest.

    Args:
        max_completed: Override the max completed sessions limit.
                       If None, uses config value.

    Returns:
        List of (project_id, session_id) tuples that were evicted.
    """
    if max_completed is None:
        max_completed = get_max_completed_sessions()

    if max_completed < 0:
        return []  # Negative means no limit

    # First, determine what to evict while holding the lock
    lock_path = _get_lru_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    to_evict: list[tuple[str, str]] = []

    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            cache = _load_cache_unlocked()
            entries = cache.get("entries", [])

            if len(entries) <= max_completed:
                return []

            # Sort by last_accessed (oldest first)
            sorted_entries = sorted(entries, key=lambda e: e.get("last_accessed", ""))

            # Determine how many to evict
            to_evict_count = len(entries) - max_completed
            to_evict = [
                (e["project_id"], e["session_id"])
                for e in sorted_entries[:to_evict_count]
            ]
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)

    # Now evict each session (outside the lock to avoid deadlock)
    evicted = []
    for project_id, session_id in to_evict:
        evict_session(project_id, session_id)
        evicted.append((project_id, session_id))

    return evicted


def get_completed_count() -> int:
    """Get the current number of completed sessions in the LRU cache.

    Returns:
        The number of entries in the LRU cache.
    """
    cache = load_lru_cache()
    return len(cache.get("entries", []))
