"""Main Textual app for scope TUI."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static

from scope.core.session import Session
from scope.core.state import (
    delete_session,
    ensure_scope_dir,
    load_all,
    next_id,
    save_session,
)
from scope.core.tmux import (
    TmuxError,
    attach_in_split,
    create_session,
    detach_to_session,
    enable_mouse,
    has_session,
    in_tmux,
    kill_session,
    tmux_session_name,
)
from scope.tui.widgets.session_tree import SessionTable


class ScopeApp(App):
    """Scope TUI application.

    Displays all sessions and auto-refreshes on file changes.
    """

    TITLE = "scope"
    BINDINGS = [
        ("n", "new_session", "New"),
        ("x", "abort_session", "Abort"),
        ("q", "quit", "Quit"),
    ]

    # Track currently attached pane for detach functionality
    _attached_pane_id: str | None = None
    _attached_session_name: str | None = None
    CSS = """
    SessionTable {
        height: 1fr;
    }

    #empty-message {
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._watcher_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Header()
        yield SessionTable()
        yield Static("No sessions", id="empty-message")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        # Enable tmux mouse mode for pane switching
        if in_tmux():
            enable_mouse()
        self.refresh_sessions()
        self._watcher_task = asyncio.create_task(self._watch_sessions())

    async def on_unmount(self) -> None:
        """Called when the app is unmounted."""
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

    def refresh_sessions(self) -> None:
        """Reload and display all sessions."""
        sessions = load_all()
        table = self.query_one(SessionTable)
        empty_msg = self.query_one("#empty-message", Static)

        if sessions:
            table.update_sessions(sessions)
            table.display = True
            empty_msg.display = False
            # Update subtitle with running count
            running = sum(1 for s in sessions if s.state == "running")
            self.sub_title = f"{running} running"
        else:
            table.display = False
            empty_msg.display = True
            self.sub_title = "0 sessions"

    def action_new_session(self) -> None:
        """Create a new session and open it in a split pane."""
        # Check if we're running inside tmux
        if not in_tmux():
            self.notify("Not running inside tmux", severity="error")
            return

        # Detach any currently attached pane first
        if self._attached_pane_id:
            self.action_detach()

        scope_dir = ensure_scope_dir()
        session_id = next_id("")
        tmux_name = tmux_session_name(session_id)

        session = Session(
            id=session_id,
            task="",  # Will be inferred from first user message via hooks
            parent="",
            state="running",
            tmux_session=tmux_name,
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

        # Create independent tmux session with Claude Code
        try:
            create_session(
                name=tmux_name,
                command="claude",
                cwd=scope_dir.parent,  # Project root
                env={"SCOPE_SESSION_ID": session_id},
            )
            # Join the pane into current window (no nesting)
            pane_id = attach_in_split(tmux_name)
            self._attached_pane_id = pane_id
            self._attached_session_name = tmux_name
        except TmuxError as e:
            self.notify(f"Failed to create session: {e}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (enter key) to attach to session in split pane."""
        # Check if we're running inside tmux
        if not in_tmux():
            self.notify("Not running inside tmux", severity="error")
            return

        # Detach any currently attached pane first
        if self._attached_pane_id:
            self.action_detach()

        # Get the session ID from the row key
        session_id = str(event.row_key.value)
        tmux_name = tmux_session_name(session_id)

        # Check if session exists
        if not has_session(tmux_name):
            self.notify(f"Session {session_id} not found", severity="error")
            return

        # Join the pane into current window (no nesting)
        try:
            pane_id = attach_in_split(tmux_name)
            self._attached_pane_id = pane_id
            self._attached_session_name = tmux_name
        except TmuxError as e:
            self.notify(f"Failed to attach: {e}", severity="error")

    def action_detach(self) -> None:
        """Detach the currently attached pane back to its own session."""
        if not self._attached_pane_id or not self._attached_session_name:
            return

        try:
            detach_to_session(self._attached_pane_id, self._attached_session_name)
        except TmuxError:
            pass  # Pane might already be gone
        finally:
            self._attached_pane_id = None
            self._attached_session_name = None

    def action_abort_session(self) -> None:
        """Abort the currently selected session."""
        import subprocess

        table = self.query_one(SessionTable)

        # Get selected row
        if table.cursor_row is None:
            self.notify("No session selected", severity="warning")
            return

        row_key = table.get_row_at(table.cursor_row)
        if not row_key:
            self.notify("No session selected", severity="warning")
            return

        session_id = row_key[0]  # First column is ID (may be indented)
        session_id = session_id.strip()  # Remove indentation
        tmux_name = tmux_session_name(session_id)

        # If this session is currently attached, kill the pane first
        if self._attached_session_name == tmux_name and self._attached_pane_id:
            subprocess.run(
                ["tmux", "kill-pane", "-t", self._attached_pane_id],
                capture_output=True,
            )
            self._attached_pane_id = None
            self._attached_session_name = None

        # Kill tmux session if it exists
        if has_session(tmux_name):
            try:
                kill_session(tmux_name)
            except TmuxError as e:
                self.notify(f"Warning: {e}", severity="warning")

        # Delete session from filesystem
        try:
            delete_session(session_id)
        except FileNotFoundError:
            pass  # Already gone

        self.refresh_sessions()

    async def _watch_sessions(self) -> None:
        """Watch .scope/ for changes and refresh."""
        from watchfiles import awatch

        scope_dir = Path.cwd() / ".scope"

        # Ensure directory exists for watching
        scope_dir.mkdir(parents=True, exist_ok=True)

        try:
            async for changes in awatch(scope_dir):
                # Check if .scope was deleted (watch will stop)
                if not scope_dir.exists():
                    scope_dir.mkdir(parents=True, exist_ok=True)
                self.refresh_sessions()
        except asyncio.CancelledError:
            pass
        except FileNotFoundError:
            # Directory was deleted, recreate and restart watching
            scope_dir.mkdir(parents=True, exist_ok=True)
            self.refresh_sessions()
            # Restart the watcher
            self._watcher_task = asyncio.create_task(self._watch_sessions())
