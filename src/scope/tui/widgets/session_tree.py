"""Session list widget for scope TUI."""

from textual.widgets import DataTable

from scope.core.session import Session


class SessionTable(DataTable):
    """DataTable widget displaying scope sessions.

    Columns: ID, Task, Status, Activity
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

        for session in sessions:
            task = session.task if session.task else "(pending...)"
            # Truncate long tasks
            if len(task) > 40:
                task = task[:37] + "..."

            # Get activity from session directory if it exists
            activity = self._get_activity(session.id)

            self.add_row(
                session.id,
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
