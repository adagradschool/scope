"""Main Textual app for scope TUI."""

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from scope.core.state import load_all
from scope.tui.widgets.session_tree import SessionTable


class ScopeApp(App):
    """Scope TUI application.

    Displays all sessions and auto-refreshes on file changes.
    """

    TITLE = "scope"
    BINDINGS = [
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

    async def _watch_sessions(self) -> None:
        """Watch .scope/sessions/ for changes and refresh."""
        from watchfiles import awatch

        sessions_dir = Path.cwd() / ".scope" / "sessions"

        # Ensure directory exists for watching
        sessions_dir.mkdir(parents=True, exist_ok=True)

        try:
            async for _ in awatch(sessions_dir):
                self.refresh_sessions()
        except asyncio.CancelledError:
            pass
