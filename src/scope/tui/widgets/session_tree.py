"""Session list widget for scope TUI."""

from collections import defaultdict

from textual.widgets import DataTable

from scope.core.session import Session


def _build_tree(
    sessions: list[Session],
    collapsed: set[str],
    hide_done: bool = False,
) -> list[tuple[Session, int, bool]]:
    """Build tree structure from flat session list.

    Args:
        sessions: Flat list of sessions.
        collapsed: Set of session IDs that are collapsed.
        hide_done: Whether to hide done/aborted sessions.

    Returns:
        List of (session, depth, has_children) tuples in display order (DFS).
    """
    # Filter out done/aborted if requested
    if hide_done:
        # Build set of IDs to hide (done/aborted/exited sessions and their descendants)
        hidden_ids: set[str] = set()
        for s in sessions:
            if s.state in {"done", "aborted", "exited"}:
                hidden_ids.add(s.id)
        # Also hide children of hidden sessions
        changed = True
        while changed:
            changed = False
            for s in sessions:
                if s.parent in hidden_ids and s.id not in hidden_ids:
                    hidden_ids.add(s.id)
                    changed = True
        sessions = [s for s in sessions if s.id not in hidden_ids]

    # Group sessions by parent
    children: dict[str, list[Session]] = defaultdict(list)
    for session in sessions:
        children[session.parent].append(session)

    # Sort children by ID within each parent group (numeric segment ordering)
    for parent_id in children:
        children[parent_id].sort(key=lambda s: [int(x) for x in s.id.split(".")])

    # DFS traversal starting from root sessions (parent="")
    result: list[tuple[Session, int, bool]] = []

    def traverse(parent: str, depth: int) -> None:
        for session in children.get(parent, []):
            has_children = bool(children.get(session.id))
            result.append((session, depth, has_children))
            # Skip children if this node is collapsed
            if session.id not in collapsed:
                traverse(session.id, depth + 1)

    traverse("", 0)
    return result


class SessionTable(DataTable):
    """DataTable widget displaying scope sessions.

    Columns: ID, Task, Status, Activity
    Sessions are displayed in tree hierarchy with indentation.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._collapsed: set[str] = set()
        self._sessions: list[Session] = []
        self._hide_done: bool = False
        self._selected_session_id: str | None = None

    def on_mount(self) -> None:
        """Set up the table columns on mount."""
        self.add_columns("ID", "Task", "Status", "Activity")
        self.cursor_type = "row"

    def watch_cursor_row(self, old_row: int | None, new_row: int | None) -> None:
        """Track cursor changes to preserve selection across refreshes."""
        if new_row is not None and self.row_count > 0:
            try:
                row = self.get_row_at(new_row)
                if row is not None:
                    display_id = row[0]
                    session_id = display_id.lstrip("▶▼ ").strip()
                    if session_id:
                        self._selected_session_id = session_id
            except Exception:
                pass

    def toggle_collapse(self) -> None:
        """Toggle collapse state on currently selected session."""
        if self.cursor_row is None:
            return

        row_key = self.get_row_at(self.cursor_row)
        if not row_key:
            return

        # Extract session ID from first column (may have indicator prefix)
        display_id = row_key[0]
        session_id = display_id.lstrip("▶▼ ").strip()

        if session_id in self._collapsed:
            self._collapsed.remove(session_id)
        else:
            self._collapsed.add(session_id)

        # Re-render with updated collapse state
        self._render_sessions()

    def update_sessions(self, sessions: list[Session], hide_done: bool = False) -> None:
        """Update the table with the given sessions.

        Args:
            sessions: List of sessions to display.
            hide_done: Whether to hide done/aborted sessions.
        """
        self._sessions = sessions
        self._hide_done = hide_done
        self._render_sessions()

    def set_selected_session(self, session_id: str | None) -> None:
        """Set the selected session ID for the next render."""
        self._selected_session_id = session_id

    def _render_sessions(self) -> None:
        """Render sessions to the table."""
        # Preserve current cursor selection before clearing rows.
        # Skip if _selected_session_id is already set (e.g., by set_selected_session).
        if (
            self._selected_session_id is None
            and self.cursor_row is not None
            and self.row_count > 0
        ):
            try:
                row = self.get_row_at(self.cursor_row)
                if row is not None:
                    display_id = row[0]
                    session_id = display_id.lstrip("▶▼ ").strip()
                    if session_id:
                        self._selected_session_id = session_id
            except Exception:
                pass

        # Use stored selection (tracked by watch_cursor_row or cursor_row above)
        selected_session_id = self._selected_session_id

        self.clear()

        # Build tree and iterate in display order
        tree = _build_tree(self._sessions, self._collapsed, self._hide_done)

        for session, depth, has_children in tree:
            task = session.task if session.task else "(pending...)"
            # Truncate long tasks
            if len(task) > 40:
                task = task[:37] + "..."

            # Get activity from session directory if it exists
            activity = self._get_activity(session.id, session.state)

            # Add indentation and tree indicator for nested sessions
            indent = "  " * depth
            if has_children:
                indicator = "▶ " if session.id in self._collapsed else "▼ "
            else:
                indicator = "  "
            display_id = f"{indent}{indicator}{session.id}"

            self.add_row(
                display_id,
                task,
                session.state,
                activity,
                key=session.id,
            )

        # Restore selection if the session still exists
        if selected_session_id is not None:
            # Try the selected session, then walk up to parents
            session_id = selected_session_id
            while session_id:
                try:
                    row_index = self.get_row_index(session_id)
                    self.move_cursor(row=row_index)
                    self._selected_session_id = session_id
                    break
                except Exception:
                    # Session not found, try parent (e.g., "0.1.2" -> "0.1" -> "0")
                    if "." in session_id:
                        session_id = session_id.rsplit(".", 1)[0]
                    else:
                        # No parent, clear stored selection
                        self._selected_session_id = None
                        break

    def _get_activity(self, session_id: str, session_state: str) -> str:
        """Get the current activity for a session.

        Args:
            session_id: The session ID.
            session_state: The session state.

        Returns:
            Activity string or "-" if none.
        """
        from scope.core.state import ensure_scope_dir

        scope_dir = ensure_scope_dir()
        activity_file = scope_dir / "sessions" / session_id / "activity"
        if activity_file.exists():
            activity = ""
            for line in activity_file.read_text().splitlines():
                if line.strip():
                    activity = line.strip()
            if activity:
                if session_state in {"done", "aborted", "exited"}:
                    activity = _past_tense_activity(activity)
                # Truncate long activity
                if len(activity) > 30:
                    return activity[:27] + "..."
                return activity
        return "-"


def _past_tense_activity(activity: str) -> str:
    """Convert present-tense activity to past tense for done sessions."""
    conversions = {
        "reading ": "read ",
        "editing ": "edited ",
        "running: ": "ran: ",
        "searching: ": "searched: ",
        "spawning subtask": "spawned subtask",
        "finding: ": "found: ",
        "reading file": "read file",
        "editing file": "edited file",
        "running command": "ran command",
        "searching": "searched",
        "finding files": "found files",
    }
    for prefix, replacement in conversions.items():
        if activity.startswith(prefix):
            return replacement + activity[len(prefix) :]
    return activity
