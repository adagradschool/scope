"""State management for scope sessions.

All session data is stored in .scope/sessions/{id}/ with individual files:
- task: One-line task description
- state: Current state (running, done, aborted)
- parent: Parent session ID (empty for root)
- tmux: tmux session name
- created_at: ISO format timestamp
"""

from datetime import datetime
from pathlib import Path

from scope.core.session import Session


def ensure_scope_dir() -> Path:
    """Ensure .scope directory exists in current working directory.

    Creates .scope/ and .scope/sessions/ if they don't exist.

    Returns:
        Path to .scope directory.
    """
    scope_dir = Path.cwd() / ".scope"
    sessions_dir = scope_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return scope_dir


def _get_next_id_path(scope_dir: Path) -> Path:
    """Get path to next_id counter file."""
    return scope_dir / "next_id"


def _get_session_dir(scope_dir: Path, session_id: str) -> Path:
    """Get path to session directory."""
    return scope_dir / "sessions" / session_id


def next_id(parent: str = "") -> str:
    """Get the next available session ID.

    ID format:
    - Root sessions: "0", "1", "2", ...
    - Child sessions: "{parent}.0", "{parent}.1", ...

    Args:
        parent: Parent session ID. Empty string for root sessions.

    Returns:
        The next available session ID.
    """
    scope_dir = ensure_scope_dir()

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


def load_session(session_id: str) -> Session | None:
    """Load a session by ID.

    Args:
        session_id: The session ID to load.

    Returns:
        Session object if found, None if session directory doesn't exist.
    """
    scope_dir = Path.cwd() / ".scope"
    session_dir = _get_session_dir(scope_dir, session_id)

    if not session_dir.exists():
        return None

    return Session(
        id=session_id,
        task=(session_dir / "task").read_text(),
        parent=(session_dir / "parent").read_text(),
        state=(session_dir / "state").read_text(),
        tmux_session=(session_dir / "tmux").read_text(),
        created_at=datetime.fromisoformat((session_dir / "created_at").read_text()),
    )


def load_all() -> list[Session]:
    """Load all sessions from .scope/sessions/.

    Returns:
        List of all sessions, sorted by created_at (oldest first).
        Returns empty list if .scope/sessions/ doesn't exist.
    """
    scope_dir = Path.cwd() / ".scope"
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
        state: New state value (running, done, aborted).

    Raises:
        FileNotFoundError: If session doesn't exist.
    """
    scope_dir = Path.cwd() / ".scope"
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

    scope_dir = Path.cwd() / ".scope"
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
