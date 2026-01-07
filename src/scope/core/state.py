"""State management for scope sessions.

All session data is stored in ~/.scope/repos/{dirname}-{hash}/sessions/{id}/ with individual files:
- task: One-line task description
- state: Current state (running, done, aborted, exited)
- parent: Parent session ID (empty for root)
- tmux: tmux session name
- created_at: ISO format timestamp

Sessions are scoped by git repository root (or cwd if not in a git repo).
"""

import fcntl
from datetime import datetime
from pathlib import Path

from scope.core.project import get_global_scope_base, get_root_path
from scope.core.session import Session

# Re-export for backwards compatibility
__all__ = ["get_root_path", "get_global_scope_base"]


def ensure_scope_dir() -> Path:
    """Ensure scope directory exists.

    Creates ~/.scope/repos/{identifier}/sessions/ if it doesn't exist.

    Returns:
        Path to scope directory.
    """
    scope_dir = get_global_scope_base()
    sessions_dir = scope_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return scope_dir


def _get_next_id_path(scope_dir: Path) -> Path:
    """Get path to next_id counter file."""
    return scope_dir / "next_id"


def _get_session_dir(scope_dir: Path, session_id: str) -> Path:
    """Get path to session directory."""
    return scope_dir / "sessions" / session_id


def _get_lock_path(scope_dir: Path) -> Path:
    """Get path to the lock file for atomic ID generation."""
    return scope_dir / "next_id.lock"


def next_id(parent: str = "") -> str:
    """Get the next available session ID.

    ID format:
    - Root sessions: "0", "1", "2", ...
    - Child sessions: "{parent}.0", "{parent}.1", ...

    Uses file locking to prevent race conditions when multiple processes
    call next_id() concurrently.

    Args:
        parent: Parent session ID. Empty string for root sessions.

    Returns:
        The next available session ID.
    """
    scope_dir = ensure_scope_dir()
    lock_path = _get_lock_path(scope_dir)

    # Use file locking to make the read-modify-write atomic
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            if parent:
                # Child session: find next child index for this parent
                sessions_dir = scope_dir / "sessions"
                prefix = f"{parent}."
                max_child = -1

                if sessions_dir.exists():
                    for session_dir in sessions_dir.iterdir():
                        if session_dir.is_dir() and session_dir.name.startswith(prefix):
                            # Extract child index: "0.1.2" with parent "0.1" -> "2"
                            suffix = session_dir.name[len(prefix) :]
                            # Only consider direct children (no dots in suffix)
                            if "." not in suffix:
                                try:
                                    child_idx = int(suffix)
                                    max_child = max(max_child, child_idx)
                                except ValueError:
                                    pass

                return f"{parent}.{max_child + 1}"
            else:
                # Root session: use global counter
                next_id_path = _get_next_id_path(scope_dir)

                if next_id_path.exists():
                    current = int(next_id_path.read_text().strip())
                else:
                    current = 0

                # Increment and save
                next_id_path.write_text(str(current + 1))

                return str(current)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def save_session(session: Session) -> None:
    """Save session to filesystem.

    Creates .scope/sessions/{id}/ directory with individual files:
    - task: Task description
    - state: Current state
    - parent: Parent ID (may be empty)
    - tmux: tmux session name
    - created_at: ISO format timestamp

    Args:
        session: Session to save.
    """
    scope_dir = ensure_scope_dir()
    session_dir = _get_session_dir(scope_dir, session.id)
    session_dir.mkdir(parents=True, exist_ok=True)

    # Write individual files
    (session_dir / "task").write_text(session.task)
    (session_dir / "state").write_text(session.state)
    (session_dir / "parent").write_text(session.parent)
    (session_dir / "tmux").write_text(session.tmux_session)
    (session_dir / "created_at").write_text(session.created_at.isoformat())
    (session_dir / "alias").write_text(session.alias)

    # Write depends_on file (comma-separated IDs, skip if empty)
    if session.depends_on:
        (session_dir / "depends_on").write_text(",".join(session.depends_on))
    else:
        # Remove file if it exists and depends_on is empty
        depends_on_file = session_dir / "depends_on"
        if depends_on_file.exists():
            depends_on_file.unlink()


def _get_scope_dir() -> Path:
    """Get the scope directory.

    Returns:
        Path to scope directory.
    """
    return get_global_scope_base()


def load_session(session_id: str) -> Session | None:
    """Load a session by ID.

    Args:
        session_id: The session ID to load.

    Returns:
        Session object if found, None if session directory doesn't exist.
    """
    scope_dir = _get_scope_dir()
    session_dir = _get_session_dir(scope_dir, session_id)

    if not session_dir.exists():
        return None

    # Read alias (may not exist for older sessions)
    alias_file = session_dir / "alias"
    alias = alias_file.read_text() if alias_file.exists() else ""

    # Read depends_on (may not exist for older sessions)
    depends_on_file = session_dir / "depends_on"
    depends_on: list[str] = []
    if depends_on_file.exists():
        content = depends_on_file.read_text().strip()
        if content:
            depends_on = content.split(",")

    return Session(
        id=session_id,
        task=(session_dir / "task").read_text(),
        parent=(session_dir / "parent").read_text(),
        state=(session_dir / "state").read_text(),
        tmux_session=(session_dir / "tmux").read_text(),
        created_at=datetime.fromisoformat((session_dir / "created_at").read_text()),
        alias=alias,
        depends_on=depends_on,
    )


def load_all() -> list[Session]:
    """Load all sessions from the current instance's sessions directory.

    Returns:
        List of all sessions, sorted by created_at (oldest first).
        Returns empty list if sessions directory doesn't exist.
    """
    scope_dir = _get_scope_dir()
    sessions_dir = scope_dir / "sessions"

    if not sessions_dir.exists():
        return []

    sessions = []
    for session_dir in sessions_dir.iterdir():
        if session_dir.is_dir():
            session = load_session(session_dir.name)
            if session:
                sessions.append(session)

    return sorted(sessions, key=lambda s: s.created_at)


def update_state(session_id: str, state: str) -> None:
    """Update the state of a session.

    Args:
        session_id: The session ID to update.
        state: New state value (running, done, aborted, exited).

    Raises:
        FileNotFoundError: If session doesn't exist.
    """
    scope_dir = _get_scope_dir()
    session_dir = _get_session_dir(scope_dir, session_id)

    if not session_dir.exists():
        raise FileNotFoundError(f"Session {session_id} not found")

    (session_dir / "state").write_text(state)


def delete_session(session_id: str) -> None:
    """Delete a session from the filesystem.

    Args:
        session_id: The session ID to delete.

    Raises:
        FileNotFoundError: If session doesn't exist.
    """
    import shutil

    scope_dir = _get_scope_dir()
    session_dir = _get_session_dir(scope_dir, session_id)

    if not session_dir.exists():
        raise FileNotFoundError(f"Session {session_id} not found")

    shutil.rmtree(session_dir)


def get_descendants(session_id: str) -> list[Session]:
    """Get all descendant sessions (children, grandchildren, etc.).

    Args:
        session_id: The parent session ID.

    Returns:
        List of all descendant sessions, sorted deepest-first (for safe deletion).
    """
    all_sessions = load_all()
    descendants = []

    prefix = f"{session_id}."
    for session in all_sessions:
        if session.id.startswith(prefix):
            descendants.append(session)

    # Sort by depth (deepest first) for safe deletion order
    # Depth is determined by number of dots in the ID
    return sorted(descendants, key=lambda s: s.id.count("."), reverse=True)


def resolve_id(id_or_alias: str) -> str | None:
    """Resolve a session ID or alias to a session ID.

    Args:
        id_or_alias: Either a numeric session ID (e.g., "0", "0.1") or an alias.

    Returns:
        The session ID if found, None otherwise.
    """
    # First, try as a direct session ID
    session = load_session(id_or_alias)
    if session is not None:
        return id_or_alias

    # Try as an alias
    session = load_session_by_alias(id_or_alias)
    if session is not None:
        return session.id

    return None


def load_session_by_alias(alias: str) -> Session | None:
    """Load a session by its alias.

    Args:
        alias: The alias to look up.

    Returns:
        Session object if found, None if no session with that alias exists.
    """
    if not alias:
        return None

    all_sessions = load_all()
    for session in all_sessions:
        if session.alias == alias:
            return session

    return None


def get_dependencies(session_id: str) -> list[str]:
    """Get the list of dependency IDs for a session.

    Args:
        session_id: The session ID to look up.

    Returns:
        List of session IDs that this session depends on.
        Returns empty list if session not found or has no dependencies.
    """
    session = load_session(session_id)
    if session is None:
        return []
    return session.depends_on


def save_failed_reason(session_id: str, reason: str) -> None:
    """Save the failure reason for a session.

    Args:
        session_id: The session ID to save the reason for.
        reason: The failure reason string.

    Raises:
        FileNotFoundError: If session doesn't exist.
    """
    scope_dir = _get_scope_dir()
    session_dir = _get_session_dir(scope_dir, session_id)

    if not session_dir.exists():
        raise FileNotFoundError(f"Session {session_id} not found")

    (session_dir / "failed_reason").write_text(reason)


def get_failed_reason(session_id: str) -> str | None:
    """Get the failure reason for a session.

    Args:
        session_id: The session ID to look up.

    Returns:
        The failure reason string if available, None otherwise.
    """
    scope_dir = _get_scope_dir()
    session_dir = _get_session_dir(scope_dir, session_id)

    failed_reason_file = session_dir / "failed_reason"
    if failed_reason_file.exists():
        return failed_reason_file.read_text()
    return None


def load_trajectory(session_id: str) -> list[dict] | None:
    """Load the full trajectory for a session.

    Args:
        session_id: The session ID to load trajectory for.

    Returns:
        List of trajectory entries (parsed JSONL), or None if not found.
    """
    import orjson

    scope_dir = _get_scope_dir()
    session_dir = _get_session_dir(scope_dir, session_id)

    trajectory_file = session_dir / "trajectory.jsonl"
    if not trajectory_file.exists():
        return None

    entries = []
    with trajectory_file.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(orjson.loads(line))
            except (orjson.JSONDecodeError, ValueError):
                continue

    return entries


def load_trajectory_index(session_id: str) -> dict | None:
    """Load the trajectory index for a session.

    Args:
        session_id: The session ID to load index for.

    Returns:
        Dictionary with trajectory statistics, or None if not found.
    """
    import orjson

    scope_dir = _get_scope_dir()
    session_dir = _get_session_dir(scope_dir, session_id)

    index_file = session_dir / "trajectory_index.json"
    if not index_file.exists():
        return None

    try:
        return orjson.loads(index_file.read_bytes())
    except (orjson.JSONDecodeError, ValueError):
        return None


def has_trajectory(session_id: str) -> bool:
    """Check if a session has a stored trajectory.

    Args:
        session_id: The session ID to check.

    Returns:
        True if trajectory exists, False otherwise.
    """
    scope_dir = _get_scope_dir()
    session_dir = _get_session_dir(scope_dir, session_id)

    return (session_dir / "trajectory.jsonl").exists()
