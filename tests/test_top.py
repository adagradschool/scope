"""Tests for scope TUI."""

from datetime import datetime, timezone
from unittest.mock import patch
import pytest

from scope.core.session import Session
from scope.core.state import load_all, save_session
from scope.tui.app import ScopeApp
from scope.tui.widgets.session_tree import SessionTable, _build_tree


@pytest.mark.asyncio
async def test_app_launches(mock_scope_base):
    """Test that the app launches without error."""
    app = ScopeApp()
    async with app.run_test() as pilot:
        # App should be running
        assert app.is_running


@pytest.mark.asyncio
async def test_app_shows_empty_message(mock_scope_base):
    """Test that empty state shows message."""
    app = ScopeApp()
    async with app.run_test() as pilot:
        # Table should be hidden when no sessions
        table = app.query_one(SessionTable)
        assert table.display is False


@pytest.mark.asyncio
async def test_app_displays_sessions(mock_scope_base):
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
async def test_app_quit_binding(mock_scope_base):
    """Test that Ctrl+C quits the app."""
    app = ScopeApp()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+c")
        await pilot.press("y")
        # App should have exited
        assert not app.is_running


@pytest.mark.asyncio
async def test_app_quit_keeps_running_sessions(mock_scope_base):
    """Test that quitting the app keeps running sessions."""
    # Create a running session
    running_session = Session(
        id="0",
        task="Running task",
        parent="",
        state="running",
        tmux_session="w0",
        created_at=datetime.now(timezone.utc),
    )
    # Create a done session (should not be affected)
    done_session = Session(
        id="1",
        task="Done task",
        parent="",
        state="done",
        tmux_session="w1",
        created_at=datetime.now(timezone.utc),
    )
    save_session(running_session)
    save_session(done_session)

    # Verify both sessions exist
    sessions = load_all()
    assert len(sessions) == 2

    app = ScopeApp()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+c")
        await pilot.press("y")

    # Sessions should be preserved
    sessions = load_all()
    assert len(sessions) == 2
    session_ids = {session.id for session in sessions}
    assert session_ids == {"0", "1"}


@pytest.mark.asyncio
async def test_app_shows_running_count(mock_scope_base):
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
async def test_session_table_shows_pending_task(mock_scope_base):
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
async def test_session_table_shows_activity(mock_scope_base):
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
    activity_file = mock_scope_base / "sessions" / "0" / "activity"
    activity_file.write_text("editing main.py")

    app = ScopeApp()
    async with app.run_test() as pilot:
        table = app.query_one(SessionTable)
        row_data = table.get_row_at(0)
        assert row_data[3] == "editing main.py"


@pytest.mark.asyncio
async def test_session_table_truncates_long_task(mock_scope_base):
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


@pytest.mark.asyncio
async def test_new_session_outside_tmux_shows_notification(mock_scope_base):
    """Test that pressing n outside tmux shows error notification."""
    app = ScopeApp()
    async with app.run_test() as pilot:
        # Mock in_tmux to return False (not in tmux)
        with patch("scope.tui.app.in_tmux", return_value=False):
            await pilot.press("n")

        # No session should be created
        sessions = load_all()
        assert len(sessions) == 0


@pytest.mark.asyncio
async def test_new_session_creates_session(mock_scope_base):
    """Test that pressing n creates a new session when in tmux."""
    app = ScopeApp()
    async with app.run_test() as pilot:
        # Mock in_tmux to return True (in tmux)
        # Mock create_window and attach_in_split to avoid actually creating tmux sessions
        with (
            patch("scope.tui.app.in_tmux", return_value=True),
            patch("scope.tui.app.create_window") as mock_create,
            patch("scope.tui.app.attach_in_split") as mock_attach,
        ):
            await pilot.press("n")

            # Session should be created
            sessions = load_all()
            assert len(sessions) == 1
            assert sessions[0].id == "0"
            assert sessions[0].task == ""
            assert sessions[0].state == "running"

            # create_window should have been called
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["name"] == "w0"
            assert call_kwargs["command"] == "claude"
            assert call_kwargs["env"] == {"SCOPE_SESSION_ID": "0"}

            # attach_in_split should have been called
            mock_attach.assert_called_once_with("w0")


@pytest.mark.asyncio
async def test_new_session_appears_in_table(mock_scope_base):
    """Test that new session appears in table after creation."""
    app = ScopeApp()
    async with app.run_test() as pilot:
        with (
            patch("scope.tui.app.in_tmux", return_value=True),
            patch("scope.tui.app.create_window"),
            patch("scope.tui.app.attach_in_split"),
        ):
            await pilot.press("n")

            # Trigger a refresh (file watcher would do this normally)
            app.refresh_sessions()

            table = app.query_one(SessionTable)
            assert table.row_count == 1
            row_data = table.get_row_at(0)
            assert row_data[0] == "  0"  # ID with indicator space (no children)
            assert row_data[1] == "(pending...)"  # Task (empty shows pending)


def test_build_tree_empty():
    """Test _build_tree with no sessions."""
    result = _build_tree([], collapsed=set())
    assert result == []


def test_build_tree_single_root():
    """Test _build_tree with a single root session."""
    session = Session(
        id="0",
        task="Root task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    result = _build_tree([session], collapsed=set())
    assert len(result) == 1
    # Returns (session, depth, has_children)
    assert result[0] == (session, 0, False)


def test_build_tree_with_children():
    """Test _build_tree with parent and children."""
    parent = Session(
        id="0",
        task="Parent task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    child1 = Session(
        id="0.0",
        task="Child 1",
        parent="0",
        state="running",
        tmux_session="scope-0.0",
        created_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    child2 = Session(
        id="0.1",
        task="Child 2",
        parent="0",
        state="done",
        tmux_session="scope-0.1",
        created_at=datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
    )

    # Order shouldn't matter for input
    result = _build_tree([child2, parent, child1], collapsed=set())

    # Output should be parent first, then children sorted by ID
    assert len(result) == 3
    assert result[0] == (parent, 0, True)  # has_children=True
    assert result[1] == (child1, 1, False)
    assert result[2] == (child2, 1, False)


def test_build_tree_nested():
    """Test _build_tree with deeply nested sessions."""
    root = Session(
        id="0",
        task="Root",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    child = Session(
        id="0.0",
        task="Child",
        parent="0",
        state="running",
        tmux_session="scope-0.0",
        created_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    grandchild = Session(
        id="0.0.0",
        task="Grandchild",
        parent="0.0",
        state="running",
        tmux_session="scope-0.0.0",
        created_at=datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
    )

    result = _build_tree([grandchild, root, child], collapsed=set())

    assert len(result) == 3
    assert result[0] == (root, 0, True)
    assert result[1] == (child, 1, True)
    assert result[2] == (grandchild, 2, False)


def test_build_tree_multiple_roots():
    """Test _build_tree with multiple root sessions."""
    root1 = Session(
        id="0",
        task="Root 1",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    root2 = Session(
        id="1",
        task="Root 2",
        parent="",
        state="running",
        tmux_session="scope-1",
        created_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    child_of_0 = Session(
        id="0.0",
        task="Child of 0",
        parent="0",
        state="running",
        tmux_session="scope-0.0",
        created_at=datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
    )

    result = _build_tree([child_of_0, root2, root1], collapsed=set())

    # Should be sorted: 0, 0.0, 1
    assert len(result) == 3
    assert result[0] == (root1, 0, True)
    assert result[1] == (child_of_0, 1, False)
    assert result[2] == (root2, 0, False)


def test_build_tree_collapsed():
    """Test _build_tree with collapsed nodes skips their children."""
    root = Session(
        id="0",
        task="Root",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    child = Session(
        id="0.0",
        task="Child",
        parent="0",
        state="running",
        tmux_session="scope-0.0",
        created_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    grandchild = Session(
        id="0.0.0",
        task="Grandchild",
        parent="0.0",
        state="running",
        tmux_session="scope-0.0.0",
        created_at=datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
    )

    # Collapse the root - should hide child and grandchild
    result = _build_tree([grandchild, root, child], collapsed={"0"})

    assert len(result) == 1
    assert result[0] == (root, 0, True)  # Still has_children=True

    # Collapse just the child - should show root and child but not grandchild
    result = _build_tree([grandchild, root, child], collapsed={"0.0"})

    assert len(result) == 2
    assert result[0] == (root, 0, True)
    assert result[1] == (child, 1, True)  # Still has_children=True


def test_build_tree_hide_done():
    """Test _build_tree with hide_done=True filters out done/aborted sessions."""
    root = Session(
        id="0",
        task="Running root",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    done_root = Session(
        id="1",
        task="Done root",
        parent="",
        state="done",
        tmux_session="scope-1",
        created_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    aborted_root = Session(
        id="2",
        task="Aborted root",
        parent="",
        state="aborted",
        tmux_session="scope-2",
        created_at=datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
    )
    child_of_done = Session(
        id="1.0",
        task="Child of done (still running)",
        parent="1",
        state="running",
        tmux_session="scope-1.0",
        created_at=datetime(2024, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
    )

    # With hide_done=False, all sessions visible
    result = _build_tree(
        [root, done_root, aborted_root, child_of_done], collapsed=set(), hide_done=False
    )
    assert len(result) == 4

    # With hide_done=True, done/aborted roots and their children are hidden
    result = _build_tree(
        [root, done_root, aborted_root, child_of_done], collapsed=set(), hide_done=True
    )

    assert len(result) == 1
    assert result[0] == (root, 0, False)


@pytest.mark.asyncio
async def test_session_table_shows_nested_sessions(mock_scope_base):
    """Test that nested sessions are displayed with indentation."""
    parent = Session(
        id="0",
        task="Parent task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    child = Session(
        id="0.0",
        task="Child task",
        parent="0",
        state="running",
        tmux_session="scope-0.0",
        created_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
    )
    save_session(parent)
    save_session(child)

    app = ScopeApp()
    async with app.run_test() as pilot:
        table = app.query_one(SessionTable)
        assert table.row_count == 2

        # Parent should have expand indicator (▼) since it has children
        parent_row = table.get_row_at(0)
        assert parent_row[0] == "▼ 0"

        # Child should be indented with indicator space
        child_row = table.get_row_at(1)
        assert child_row[0] == "    0.0"  # 2 spaces indent + 2 spaces indicator
