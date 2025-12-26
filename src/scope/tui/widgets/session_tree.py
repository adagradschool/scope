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
        # Build set of IDs to hide (done/aborted sessions and their descendants)
        hidden_ids: set[str] = set()
        for s in sessions:
            if s.state in {"done", "aborted"}:
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

    # Sort children by ID within each parent group
    for parent_id in children:
        children[parent_id].sort(key=lambda s: s.id)

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

    def on_mount(self) -> None:
        """Set up the table columns on mount."""
        self.add_columns("ID", "Task", "Status", "Activity")
        self.cursor_type = "row"

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

    def update_sessions(
        self, sessions: list[Session], hide_done: bool = False
    ) -> None:
        """Update the table with the given sessions.

        Args:
            sessions: List of sessions to display.
            hide_done: Whether to hide done/aborted sessions.
        """
        self._sessions = sessions
        self._hide_done = hide_done
        self._render_sessions()

    def _render_sessions(self) -> None:
        """Render sessions to the table."""
        # Save current selection before clearing
        selected_session_id: str | None = None
        if self.cursor_row is not None:
            try:
                row_key = self.get_row_at(self.cursor_row)
                if row_key:
                    selected_session_id = row_key.value
            except Exception:
                pass

        self.clear()

        # Build tree and iterate in display order
        tree = _build_tree(self._sessions, self._collapsed, self._hide_done)

        for session, depth, has_children in tree:
            task = session.task if session.task else "(pending...)"
            # Truncate long tasks
            if len(task) > 40:
                task = task[:37] + "..."

            # Get activity from session directory if it exists
            activity = self._get_activity(session.id)

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
            try:
                row_index = self.get_row_index(selected_session_id)
                self.move_cursor(row=row_index)
            except Exception:
                pass  # Session may have been removed

    def _get_activity(self, session_id: str) -> str:
        """Get the current activity for a session.

        Args:
            session_id: The session ID.

        Returns:
            Activity string or "-" if none.
        """
        from scope.core.state import ensure_scope_dir

        scope_dir = ensure_scope_dir()
        activity_file = scope_dir / "sessions" / session_id / "activity"
        if activity_file.exists():
            activity = activity_file.read_text().strip()
            if activity:
                # Truncate long activity
                if len(activity) > 30:
                    return activity[:27] + "..."
                return activity
        return "-"
