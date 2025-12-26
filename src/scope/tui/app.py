"""Main Textual app for scope TUI."""

import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static

from scope.core.session import Session
from scope.core.state import (
    delete_session,
    ensure_scope_dir,
    get_global_scope_base,
    load_all,
    next_id,
    save_session,
)
from scope.core.tmux import (
    TmuxError,
    _tmux_cmd,
    attach_in_split,
    create_window,
    detach_to_window,
    enable_mouse,
    has_window,
    in_tmux,
    kill_window,
    tmux_window_name,
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
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("space", "toggle_collapse", "Expand"),
        ("h", "toggle_hide_done", "Hide Done"),
        ("q", "quit", "Quit"),
    ]

    # Track currently attached pane for detach functionality
    _attached_pane_id: str | None = None
    _attached_window_name: str | None = None
    # Filter state
    _hide_done: bool = False
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

    def __init__(self, dangerously_skip_permissions: bool = False) -> None:
        super().__init__()
        self._watcher_task: asyncio.Task | None = None
        self._dangerously_skip_permissions = dangerously_skip_permissions

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
            table.update_sessions(sessions, hide_done=self._hide_done)
            table.display = True
            empty_msg.display = False
            # Update subtitle with running count and filter status
            running = sum(1 for s in sessions if s.state == "running")
            filter_text = " [filtered]" if self._hide_done else ""
            self.sub_title = f"{running} running{filter_text}"
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

        ensure_scope_dir()
        session_id = next_id("")
        window_name = tmux_window_name(session_id)

        session = Session(
            id=session_id,
            task="",  # Will be inferred from first user message via hooks
            parent="",
            state="running",
            tmux_session=window_name,  # Store window name (kept as tmux_session for compat)
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

        # Create tmux window with Claude Code
        try:
            command = "claude"
            if self._dangerously_skip_permissions:
                command = "claude --dangerously-skip-permissions"

            # Build environment for spawned session
            env = {"SCOPE_SESSION_ID": session_id}
            if self._dangerously_skip_permissions:
                env["SCOPE_DANGEROUSLY_SKIP_PERMISSIONS"] = "1"

            create_window(
                name=window_name,
                command=command,
                cwd=Path.cwd(),  # Project root
                env=env,
            )
            # Join the pane into current window
            pane_id = attach_in_split(window_name)
            self._attached_pane_id = pane_id
            self._attached_window_name = window_name
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
        window_name = tmux_window_name(session_id)

        # Check if window exists
        if not has_window(window_name):
            self.notify(f"Session {session_id} not found", severity="error")
            return

        # Join the pane into current window
        try:
            pane_id = attach_in_split(window_name)
            self._attached_pane_id = pane_id
            self._attached_window_name = window_name
        except TmuxError as e:
            self.notify(f"Failed to attach: {e}", severity="error")

    def action_detach(self) -> None:
        """Detach the currently attached pane back to its own window."""
        if not self._attached_pane_id or not self._attached_window_name:
            return

        try:
            detach_to_window(self._attached_pane_id, self._attached_window_name)
        except TmuxError:
            pass  # Pane might already be gone
        finally:
            self._attached_pane_id = None
            self._attached_window_name = None

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
        # Remove indentation and tree indicators (▶▼)
        session_id = session_id.lstrip("▶▼ ").strip()
        window_name = tmux_window_name(session_id)

        # If this session is currently attached, kill the pane first
        if self._attached_window_name == window_name and self._attached_pane_id:
            subprocess.run(
                _tmux_cmd(["kill-pane", "-t", self._attached_pane_id]),
                capture_output=True,
            )
            self._attached_pane_id = None
            self._attached_window_name = None

        # Kill tmux window if it exists
        if has_window(window_name):
            try:
                kill_window(window_name)
            except TmuxError as e:
                self.notify(f"Warning: {e}", severity="warning")

        # Delete session from filesystem
        try:
            delete_session(session_id)
        except FileNotFoundError:
            pass  # Already gone

        self.refresh_sessions()

    def action_toggle_collapse(self) -> None:
        """Toggle expand/collapse on the selected session."""
        table = self.query_one(SessionTable)
        table.toggle_collapse()

    def action_toggle_hide_done(self) -> None:
        """Toggle hiding of done/aborted sessions."""
        self._hide_done = not self._hide_done
        self.refresh_sessions()

    async def _watch_sessions(self) -> None:
        """Watch scope directory for changes and refresh."""
        from watchfiles import awatch

        scope_dir = get_global_scope_base()

        # Ensure directory exists for watching
        scope_dir.mkdir(parents=True, exist_ok=True)

        try:
            async for changes in awatch(scope_dir):
                # Check if scope dir was deleted (watch will stop)
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
