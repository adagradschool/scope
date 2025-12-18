"""Main Textual app for scope TUI."""

import asyncio
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from scope.core.session import Session
from scope.core.state import ensure_scope_dir, load_all, next_id, save_session
from scope.core.tmux import get_current_session, split_window
from scope.tui.widgets.session_tree import SessionTable


class ScopeApp(App):
    """Scope TUI application.

    Displays all sessions and auto-refreshes on file changes.
    """

    TITLE = "scope"
    BINDINGS = [
        ("n", "new_session", "New"),
        ("q", "quit", "Quit"),
    ]
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
        """Create a new session in a split pane."""
        # Check if we're running inside tmux
        if get_current_session() is None:
            self.notify(
                "Run scope top inside tmux to create sessions", severity="error"
            )
            return

        scope_dir = ensure_scope_dir()
        session_id = next_id("")

        session = Session(
            id=session_id,
            task="",  # Will be inferred from first user message via hooks
            parent="",
            state="running",
            tmux_session=f"scope-{session_id}",
            created_at=datetime.now(),
        )
        save_session(session)

        # Split current window to run claude with session ID
        split_window(
            command="claude",
            cwd=scope_dir.parent,  # Project root
            env={"SCOPE_SESSION_ID": session_id},
        )

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
