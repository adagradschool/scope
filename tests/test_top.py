"""Tests for scope top TUI."""

from datetime import datetime, timezone

import pytest

from scope.core.session import Session
from scope.core.state import save_session
from scope.tui.app import ScopeApp
from scope.tui.widgets.session_tree import SessionTable


@pytest.fixture
def setup_scope_dir(tmp_path, monkeypatch):
    """Set up a temporary scope directory."""
    monkeypatch.chdir(tmp_path)
    scope_dir = tmp_path / ".scope" / "sessions"
    scope_dir.mkdir(parents=True)
    return tmp_path


@pytest.mark.asyncio
async def test_app_launches(setup_scope_dir):
    """Test that the app launches without error."""
    app = ScopeApp()
    async with app.run_test() as pilot:
        # App should be running
        assert app.is_running


@pytest.mark.asyncio
async def test_app_shows_empty_message(setup_scope_dir):
    """Test that empty state shows message."""
    app = ScopeApp()
    async with app.run_test() as pilot:
        # Table should be hidden when no sessions
        table = app.query_one(SessionTable)
        assert table.display is False


@pytest.mark.asyncio
async def test_app_displays_sessions(setup_scope_dir):
    """Test that app displays sessions."""
    # Create a session
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    app = ScopeApp()
    async with app.run_test() as pilot:
        table = app.query_one(SessionTable)
        assert table.display is True
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_app_quit_binding(setup_scope_dir):
    """Test that q quits the app."""
    app = ScopeApp()
    async with app.run_test() as pilot:
        await pilot.press("q")
        # App should have exited
        assert not app.is_running


@pytest.mark.asyncio
async def test_app_shows_running_count(setup_scope_dir):
    """Test that subtitle shows running count."""
    # Create sessions with different states
    running = Session(
        id="0",
        task="Running task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    done = Session(
        id="1",
        task="Done task",
        parent="",
        state="done",
        tmux_session="scope-1",
        created_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    save_session(running)
    save_session(done)

    app = ScopeApp()
    async with app.run_test() as pilot:
        assert "1 running" in app.sub_title


@pytest.mark.asyncio
async def test_session_table_shows_pending_task(setup_scope_dir):
    """Test that empty task shows (pending...)."""
    session = Session(
        id="0",
        task="",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    app = ScopeApp()
    async with app.run_test() as pilot:
        table = app.query_one(SessionTable)
        # Check the task column (index 1) of first row
        row_data = table.get_row_at(0)
        assert row_data[1] == "(pending...)"


@pytest.mark.asyncio
async def test_session_table_shows_activity(setup_scope_dir, tmp_path):
    """Test that activity is displayed."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    # Write activity file
    activity_file = tmp_path / ".scope" / "sessions" / "0" / "activity"
    activity_file.write_text("editing main.py")

    app = ScopeApp()
    async with app.run_test() as pilot:
        table = app.query_one(SessionTable)
        row_data = table.get_row_at(0)
        assert row_data[3] == "editing main.py"


@pytest.mark.asyncio
async def test_session_table_truncates_long_task(setup_scope_dir):
    """Test that long tasks are truncated."""
    long_task = "This is a very long task description that should be truncated"
    session = Session(
        id="0",
        task=long_task,
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    app = ScopeApp()
    async with app.run_test() as pilot:
        table = app.query_one(SessionTable)
        row_data = table.get_row_at(0)
        assert len(row_data[1]) <= 40
        assert row_data[1].endswith("...")
