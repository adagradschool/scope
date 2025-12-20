"""Session list widget for scope TUI."""

from collections import defaultdict

from textual.widgets import DataTable

from scope.core.session import Session


def _build_tree(sessions: list[Session]) -> list[tuple[Session, int]]:
    """Build tree structure from flat session list.

    Args:
        sessions: Flat list of sessions.

    Returns:
        List of (session, depth) tuples in display order (DFS).
    """
    # Group sessions by parent
    children: dict[str, list[Session]] = defaultdict(list)
    for session in sessions:
        children[session.parent].append(session)

    # Sort children by ID within each parent group
    for parent_id in children:
        children[parent_id].sort(key=lambda s: s.id)

    # DFS traversal starting from root sessions (parent="")
    result: list[tuple[Session, int]] = []

    def traverse(parent: str, depth: int) -> None:
        for session in children.get(parent, []):
            result.append((session, depth))
            traverse(session.id, depth + 1)

    traverse("", 0)
    return result


class SessionTable(DataTable):
    """DataTable widget displaying scope sessions.

    Columns: ID, Task, Status, Activity
    Sessions are displayed in tree hierarchy with indentation.
    """

    def on_mount(self) -> None:
        """Set up the table columns on mount."""
        self.add_columns("ID", "Task", "Status", "Activity")
        self.cursor_type = "row"

    def update_sessions(self, sessions: list[Session]) -> None:
        """Update the table with the given sessions.

        Args:
            sessions: List of sessions to display.
        """
        self.clear()

        # Build tree and iterate in display order
        tree = _build_tree(sessions)

        for session, depth in tree:
            task = session.task if session.task else "(pending...)"
            # Truncate long tasks
            if len(task) > 40:
                task = task[:37] + "..."

            # Get activity from session directory if it exists
            activity = self._get_activity(session.id)

            # Add indentation for nested sessions
            indent = "  " * depth
            display_id = f"{indent}{session.id}"

            self.add_row(
                display_id,
                task,
                session.state,
                activity,
                key=session.id,
            )

    def _get_activity(self, session_id: str) -> str:
        """Get the current activity for a session.

        Args:
            session_id: The session ID.

        Returns:
            Activity string or "-" if none.
        """
        from pathlib import Path

        activity_file = Path.cwd() / ".scope" / "sessions" / session_id / "activity"
        if activity_file.exists():
            activity = activity_file.read_text().strip()
            if activity:
                # Truncate long activity
                if len(activity) > 30:
                    return activity[:27] + "..."
                return activity
        return "-"
