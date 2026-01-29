"""Tests for --on-fail and --on-pass conditional branching on spawn."""

from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from scope.cli import main
from scope.core.session import Session
from scope.core.state import load_session, save_session


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def _init_next_id(mock_scope_base, value: int) -> None:
    """Initialize the next_id counter so spawned sessions get predictable IDs."""
    (mock_scope_base / "next_id").write_text(str(value))


# --- --on-fail tests ---


def test_on_fail_skips_when_dep_passed(runner, mock_scope_base, cleanup_scope_windows):
    """--on-fail session is skipped when the dependency succeeded (state=done)."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)

    result = runner.invoke(main, ["spawn", "--on-fail", "0", "Fix the build"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "skipped"


def test_on_fail_runs_when_dep_failed(runner, mock_scope_base, cleanup_scope_windows):
    """--on-fail session runs normally when the dependency failed."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="failed",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)

    result = runner.invoke(main, ["spawn", "--on-fail", "0", "Fix the build"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "running"


def test_on_fail_runs_when_dep_aborted(runner, mock_scope_base, cleanup_scope_windows):
    """--on-fail session runs when the dependency was aborted."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="aborted",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)

    result = runner.invoke(main, ["spawn", "--on-fail", "0", "Retry the build"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "running"


# --- --on-pass tests ---


def test_on_pass_skips_when_dep_failed(runner, mock_scope_base, cleanup_scope_windows):
    """--on-pass session is skipped when the dependency failed."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="failed",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)

    result = runner.invoke(main, ["spawn", "--on-pass", "0", "Deploy"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "skipped"


def test_on_pass_runs_when_dep_passed(runner, mock_scope_base, cleanup_scope_windows):
    """--on-pass session runs normally when the dependency succeeded."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)

    result = runner.invoke(main, ["spawn", "--on-pass", "0", "Deploy"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "running"


# --- Skipped status tests ---


def test_skipped_session_has_depends_on(runner, mock_scope_base, cleanup_scope_windows):
    """Skipped sessions record their dependency in depends_on."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)

    result = runner.invoke(main, ["spawn", "--on-fail", "0", "Fix"])

    session_id = result.output.strip()
    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "skipped"
    assert "0" in loaded.depends_on


def test_skipped_session_has_no_tmux(runner, mock_scope_base, cleanup_scope_windows):
    """Skipped sessions have an empty tmux_session (no window created)."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)

    result = runner.invoke(main, ["spawn", "--on-fail", "0", "Fix"])

    session_id = result.output.strip()
    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.tmux_session == ""


# --- Composition with --pipe ---


def test_on_pass_with_pipe(runner, mock_scope_base, cleanup_scope_windows):
    """--on-pass composes with --pipe: runs and injects result when dep passed."""
    dep = Session(
        id="0",
        task="Research",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="research",
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Found 3 libs.")

    result = runner.invoke(
        main, ["spawn", "--on-pass", "0", "--pipe", "0", "Use results"]
    )

    assert result.exit_code == 0
    session_id = result.output.strip()

    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "running"

    # Verify contract includes piped results
    contract = (mock_scope_base / "sessions" / session_id / "contract.md").read_text()
    assert "# Prior Results" in contract
    assert "Found 3 libs." in contract


def test_on_fail_with_pipe_skips(runner, mock_scope_base, cleanup_scope_windows):
    """--on-fail with --pipe: skipped when dep passed (pipe results not collected)."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)
    (mock_scope_base / "sessions" / "0" / "result").write_text("Build succeeded.")

    result = runner.invoke(
        main, ["spawn", "--on-fail", "0", "--pipe", "0", "Fix with context"]
    )

    assert result.exit_code == 0
    session_id = result.output.strip()

    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "skipped"


# --- Alias resolution ---


def test_on_fail_resolves_alias(runner, mock_scope_base, cleanup_scope_windows):
    """--on-fail resolves aliases to session IDs."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="failed",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="build",
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)

    result = runner.invoke(main, ["spawn", "--on-fail", "build", "Fix the build"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "running"


def test_on_pass_resolves_alias(runner, mock_scope_base, cleanup_scope_windows):
    """--on-pass resolves aliases to session IDs."""
    dep = Session(
        id="0",
        task="Build",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
        alias="build",
    )
    save_session(dep)
    _init_next_id(mock_scope_base, 1)

    result = runner.invoke(main, ["spawn", "--on-pass", "build", "Deploy"])

    assert result.exit_code == 0
    session_id = result.output.strip()

    loaded = load_session(session_id)
    assert loaded is not None
    assert loaded.state == "running"


# --- Error cases ---


def test_on_fail_not_found(runner, mock_scope_base):
    """--on-fail with non-existent session shows error."""
    result = runner.invoke(main, ["spawn", "--on-fail", "999", "Fix"])

    assert result.exit_code == 1
    assert "--on-fail session '999' not found" in result.output


def test_on_pass_not_found(runner, mock_scope_base):
    """--on-pass with non-existent session shows error."""
    result = runner.invoke(main, ["spawn", "--on-pass", "999", "Deploy"])

    assert result.exit_code == 1
    assert "--on-pass session '999' not found" in result.output


# --- Help text ---


def test_spawn_help_shows_conditional_flags(runner):
    """--on-fail and --on-pass appear in spawn help."""
    result = runner.invoke(main, ["spawn", "--help"])
    assert result.exit_code == 0
    assert "--on-fail" in result.output
    assert "--on-pass" in result.output
