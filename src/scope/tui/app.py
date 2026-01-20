"""Main Textual app for scope TUI."""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Static

from scope.core.session import Session
from scope.core.abort import abort_session_tree, session_tree_ids
from scope.core.state import (
    get_global_scope_base,
    get_root_path,
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
    get_current_session,
    get_current_pane_id,
    get_scope_session,
    get_right_pane_session_id,
    has_window,
    in_tmux,
    detach_client,
    pane_target_for_window,
    rename_current_window,
    send_keys,
    set_current_window_option,
    set_pane_option,
    select_pane,
    tmux_window_name,
)
from scope.hooks.install import install_tmux_hooks
from scope.tui.widgets.session_tree import SessionTable


class QuitConfirmScreen(ModalScreen[bool]):
    """Modal screen to confirm quitting scope."""

    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    QuitConfirmScreen {
        align: center middle;
    }

    #quit-dialog {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    #quit-message {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }

    #quit-buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #quit-buttons Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical

        with Vertical(id="quit-dialog"):
            yield Static("Quit scope? Sessions will keep running.", id="quit-message")
            with Horizontal(id="quit-buttons"):
                yield Button("Yes (y)", id="yes", variant="error")
                yield Button("No (n)", id="no", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


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
        ("ctrl+c", "quit", "Quit"),
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
        self._detach_client_on_exit = os.environ.get("SCOPE_TUI_DETACH_ON_EXIT") == "1"
        if not self._detach_client_on_exit and in_tmux():
            current = get_current_session()
            if current and current == get_scope_session():
                self._detach_client_on_exit = True

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Header()
        yield SessionTable()
        yield Static("No sessions", id="empty-message")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        repo_name = get_root_path().name
        if repo_name:
            self.title = f"scope · {repo_name}"
        # Enable tmux mouse mode for pane switching
        if in_tmux():
            enable_mouse()
            try:
                rename_current_window("scope-top")
                set_current_window_option("remain-on-exit", "off")
            except TmuxError:
                pass
        # Ensure tmux hooks are installed (they don't persist across server restarts)
        success, error = install_tmux_hooks()
        if not success:
            self.notify(f"tmux hooks: {error}", severity="warning")
        self.refresh_sessions()
        self._watcher_task = asyncio.create_task(self._watch_sessions())

    async def on_unmount(self) -> None:
        """Called when the app is unmounted."""
        # Cancel the watcher task first
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

        # Detach any attached pane back to its window (don't kill it)
        if self._attached_pane_id and self._attached_window_name:
            try:
                detach_to_window(self._attached_pane_id, self._attached_window_name)
            except TmuxError:
                pass  # Pane might already be gone
            self._attached_pane_id = None
            self._attached_window_name = None

        if self._detach_client_on_exit and in_tmux():
            try:
                detach_client()
            except TmuxError:
                pass

        # Sessions keep running - user can return with `scope` later

    def refresh_sessions(self) -> None:
        """Reload and display all sessions."""
        sessions = load_all()
        try:
            table = self.query_one(SessionTable)
            empty_msg = self.query_one("#empty-message", Static)
        except NoMatches:
            return

        if sessions:
            if in_tmux():
                right_session_id = get_right_pane_session_id()
                if right_session_id and any(
                    session.id == right_session_id for session in sessions
                ):
                    table.set_selected_session(right_session_id)
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

        session_id = next_id("")
        window_name = tmux_window_name(session_id)

        # Create tmux window with Claude Code BEFORE saving session
        # This prevents a race where load_all() sees a "running" session
        # with a tmux_session set but the window doesn't exist yet,
        # causing it to be incorrectly marked as "aborted"
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

            try:
                set_pane_option(
                    pane_target_for_window(window_name),
                    "@scope_session_id",
                    session_id,
                )
            except TmuxError:
                pass

            # Ensure tmux hook is installed AFTER create_window (so server exists)
            # Idempotent - safe to call on every spawn
            install_tmux_hooks()

            # Now that window exists, save session to filesystem
            session = Session(
                id=session_id,
                task="",  # Will be inferred from first user message via hooks
                parent="",
                state="running",
                tmux_session=window_name,  # Store window name (kept as tmux_session for compat)
                created_at=datetime.now(timezone.utc),
            )
            save_session(session)

            table = self.query_one(SessionTable)
            table.set_selected_session(session_id)
            self.refresh_sessions()

            # Join the pane into current window
            pane_id = attach_in_split(window_name)
            self._attached_pane_id = pane_id
            self._attached_window_name = window_name
            try:
                set_pane_option(pane_id, "@scope_session_id", session_id)
            except TmuxError:
                pass
            # Focus the newly created Claude Code pane
            try:
                select_pane(pane_id)
            except TmuxError:
                pass

            # Prefill /scope command (without pressing Enter)
            try:
                send_keys(pane_id, "/scope ", submit=False)
            except TmuxError:
                pass
        except TmuxError as e:
            self.notify(f"Failed to create session: {e}", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (enter key) to attach to session in split pane."""
        # Check if we're running inside tmux
        if not in_tmux():
            self.notify("Not running inside tmux", severity="error")
            return

        current_pane_id = get_current_pane_id()

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
            try:
                set_pane_option(pane_id, "@scope_session_id", session_id)
            except TmuxError:
                pass
            if current_pane_id:
                try:
                    select_pane(current_pane_id)
                except TmuxError:
                    pass
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
        session_ids = session_tree_ids(session_id)
        window_names = [tmux_window_name(sid) for sid in session_ids]

        # If this session is currently attached, kill the pane first
        if self._attached_window_name in window_names and self._attached_pane_id:
            subprocess.run(
                _tmux_cmd(["kill-pane", "-t", self._attached_pane_id]),
                capture_output=True,
            )
            self._attached_pane_id = None
            self._attached_window_name = None

        result = abort_session_tree(session_id)
        for warning in result.warnings:
            self.notify(f"Warning: {warning}", severity="warning")

        self.refresh_sessions()

    def action_toggle_collapse(self) -> None:
        """Toggle expand/collapse on the selected session."""
        table = self.query_one(SessionTable)
        table.toggle_collapse()

    def action_toggle_hide_done(self) -> None:
        """Toggle hiding of done/aborted sessions."""
        self._hide_done = not self._hide_done
        self.refresh_sessions()

    def action_quit(self) -> None:
        """Show confirmation dialog before quitting."""

        def handle_quit_response(confirmed: bool) -> None:
            if confirmed:
                self.action_detach()
                if in_tmux():
                    try:
                        set_current_window_option("remain-on-exit", "off")
                    except TmuxError:
                        pass
                self.exit()

        self.push_screen(QuitConfirmScreen(), handle_quit_response)

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
