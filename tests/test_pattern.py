"""Tests for pattern commitment feature (F4)."""

from datetime import datetime, timezone

import orjson
import pytest
from click.testing import CliRunner

from scope.core.contract import PATTERN_PHASES, generate_contract
from scope.core.session import Session
from scope.core.state import (
    advance_pattern_phase,
    load_pattern_state,
    save_pattern_state,
    save_session,
)
from scope.hooks.handler import main


# --- Pattern phases definition tests ---


def test_pattern_phases_has_tdd():
    """Test PATTERN_PHASES includes TDD with correct phases."""
    assert "tdd" in PATTERN_PHASES
    assert PATTERN_PHASES["tdd"] == ["red", "green", "refactor"]


def test_pattern_phases_has_ralph():
    """Test PATTERN_PHASES includes RALPH with correct phases."""
    assert "ralph" in PATTERN_PHASES
    assert PATTERN_PHASES["ralph"] == ["critique", "improve"]


def test_pattern_phases_has_map_reduce():
    """Test PATTERN_PHASES includes map-reduce with correct phases."""
    assert "map-reduce" in PATTERN_PHASES
    assert PATTERN_PHASES["map-reduce"] == ["map", "wait", "reduce"]


def test_pattern_phases_has_maker_checker():
    """Test PATTERN_PHASES includes maker-checker."""
    assert "maker-checker" in PATTERN_PHASES
    assert PATTERN_PHASES["maker-checker"] == ["make", "check", "fix"]


def test_pattern_phases_has_rlm():
    """Test PATTERN_PHASES includes RLM."""
    assert "rlm" in PATTERN_PHASES
    assert PATTERN_PHASES["rlm"] == ["peek", "grep", "dive"]


def test_pattern_phases_dag_has_no_phases():
    """Test PATTERN_PHASES DAG has empty phases (task-specific)."""
    assert "dag" in PATTERN_PHASES
    assert PATTERN_PHASES["dag"] == []


# --- Pattern state persistence tests ---


@pytest.fixture
def session_dir(mock_scope_base):
    """Create a session directory for testing."""
    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    return mock_scope_base / "sessions" / "0"


def test_save_pattern_state(session_dir):
    """Test saving pattern state creates the expected files."""
    save_pattern_state(
        session_id="0",
        pattern="tdd",
        phases=["red", "green", "refactor"],
    )

    assert (session_dir / "pattern_name").read_text() == "tdd"
    assert orjson.loads((session_dir / "pattern_phases").read_bytes()) == [
        "red",
        "green",
        "refactor",
    ]
    assert orjson.loads((session_dir / "pattern_completed").read_bytes()) == []
    # Default current should be first phase
    assert (session_dir / "pattern_current").read_text() == "red"


def test_save_pattern_state_with_current(session_dir):
    """Test saving pattern state with explicit current phase."""
    save_pattern_state(
        session_id="0",
        pattern="tdd",
        phases=["red", "green", "refactor"],
        current="green",
        completed=["red"],
    )

    assert (session_dir / "pattern_current").read_text() == "green"
    assert orjson.loads((session_dir / "pattern_completed").read_bytes()) == ["red"]


def test_save_pattern_state_session_not_found(mock_scope_base):
    """Test saving pattern state for nonexistent session raises."""
    with pytest.raises(FileNotFoundError):
        save_pattern_state(session_id="999", pattern="tdd", phases=["red"])


def test_load_pattern_state(session_dir):
    """Test loading pattern state returns correct dict."""
    save_pattern_state(
        session_id="0",
        pattern="ralph",
        phases=["critique", "improve"],
    )

    state = load_pattern_state("0")
    assert state is not None
    assert state["pattern"] == "ralph"
    assert state["phases"] == ["critique", "improve"]
    assert state["completed"] == []
    assert state["current"] == "critique"


def test_load_pattern_state_no_pattern(session_dir):
    """Test loading pattern state when no pattern committed returns None."""
    state = load_pattern_state("0")
    assert state is None


def test_load_pattern_state_nonexistent_session(mock_scope_base):
    """Test loading pattern state for nonexistent session returns None."""
    state = load_pattern_state("999")
    assert state is None


def test_advance_pattern_phase(session_dir):
    """Test advancing through pattern phases."""
    save_pattern_state(
        session_id="0",
        pattern="tdd",
        phases=["red", "green", "refactor"],
    )

    # Advance from red to green
    state = advance_pattern_phase("0")
    assert state is not None
    assert state["completed"] == ["red"]
    assert state["current"] == "green"

    # Advance from green to refactor
    state = advance_pattern_phase("0")
    assert state is not None
    assert state["completed"] == ["red", "green"]
    assert state["current"] == "refactor"

    # Advance from refactor to done
    state = advance_pattern_phase("0")
    assert state is not None
    assert state["completed"] == ["red", "green", "refactor"]
    assert state["current"] == ""


def test_advance_pattern_phase_no_pattern(session_dir):
    """Test advancing when no pattern is committed returns None."""
    state = advance_pattern_phase("0")
    assert state is None


# --- Contract generation with pattern ---


def test_generate_contract_with_pattern():
    """Test contract includes pattern commitment section."""
    contract = generate_contract(
        prompt="Implement feature",
        pattern="tdd",
    )

    assert "# Pattern Commitment" in contract
    assert "**tdd**" in contract
    assert "red → green → refactor" in contract
    assert "drift must be conscious" in contract


def test_generate_contract_with_pattern_no_phases():
    """Test contract with pattern that has no predefined phases."""
    contract = generate_contract(
        prompt="Build pipeline",
        pattern="dag",
    )

    assert "# Pattern Commitment" in contract
    assert "**dag**" in contract
    assert "drift must be conscious" in contract
    # Should not include phases line
    assert "→" not in contract.split("# Pattern Commitment")[1].split("# ")[0]


def test_generate_contract_pattern_none():
    """Test no pattern section when None."""
    contract = generate_contract(prompt="Do work", pattern=None)

    assert "# Pattern Commitment" not in contract


def test_generate_contract_pattern_ordering():
    """Test pattern section comes after phase and before parent intent."""
    contract = generate_contract(
        prompt="Implement feature",
        phase="RED",
        pattern="tdd",
        parent_intent="Build the auth system",
    )

    phase_idx = contract.index("# Phase")
    pattern_idx = contract.index("# Pattern Commitment")
    intent_idx = contract.index("# Parent Intent")
    task_idx = contract.index("# Task")

    assert phase_idx < pattern_idx < intent_idx < task_idx


def test_generate_contract_full_with_pattern():
    """Test all sections including pattern appear in correct order."""
    contract = generate_contract(
        prompt="Implement feature",
        depends_on=["0.0"],
        phase="GREEN",
        pattern="tdd",
        parent_intent="Build the auth system",
        prior_results=["Previous research completed."],
        file_scope=["src/auth/"],
        verify=["pytest"],
    )

    deps_idx = contract.index("# Dependencies")
    phase_idx = contract.index("# Phase")
    pattern_idx = contract.index("# Pattern Commitment")
    intent_idx = contract.index("# Parent Intent")
    results_idx = contract.index("# Prior Results")
    task_idx = contract.index("# Task")
    scope_idx = contract.index("# File Scope")
    verify_idx = contract.index("# Verification")

    assert (
        deps_idx
        < phase_idx
        < pattern_idx
        < intent_idx
        < results_idx
        < task_idx
        < scope_idx
        < verify_idx
    )


# --- Pattern re-injection hook tests ---


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def setup_session(mock_scope_base, monkeypatch):
    """Set up a session with environment configured."""
    monkeypatch.setenv("SCOPE_SESSION_ID", "0")

    session = Session(
        id="0",
        task="Test task",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    return mock_scope_base / "sessions" / "0"


def test_pattern_reinject_outputs_state(runner, setup_session):
    """Test pattern-reinject hook outputs pattern state to stderr."""
    save_pattern_state(
        session_id="0",
        pattern="tdd",
        phases=["red", "green", "refactor"],
    )

    result = runner.invoke(main, ["pattern-reinject"])

    assert result.exit_code == 0
    assert "[pattern-state]" in result.output
    assert "Pattern: tdd" in result.output
    assert "Next: red" in result.output
    assert "red → green → refactor" in result.output


def test_pattern_reinject_shows_completed(runner, setup_session):
    """Test pattern-reinject shows completed phases."""
    save_pattern_state(
        session_id="0",
        pattern="tdd",
        phases=["red", "green", "refactor"],
        completed=["red"],
        current="green",
    )

    result = runner.invoke(main, ["pattern-reinject"])

    assert result.exit_code == 0
    assert "Completed: red" in result.output
    assert "Next: green" in result.output


def test_pattern_reinject_all_complete(runner, setup_session):
    """Test pattern-reinject when all phases are complete."""
    save_pattern_state(
        session_id="0",
        pattern="tdd",
        phases=["red", "green", "refactor"],
        completed=["red", "green", "refactor"],
        current="",
    )

    result = runner.invoke(main, ["pattern-reinject"])

    assert result.exit_code == 0
    assert "All phases complete" in result.output


def test_pattern_reinject_no_pattern(runner, setup_session):
    """Test pattern-reinject with no pattern committed exits silently."""
    result = runner.invoke(main, ["pattern-reinject"])

    assert result.exit_code == 0
    assert result.output == ""


def test_pattern_reinject_no_session(runner, mock_scope_base, monkeypatch):
    """Test pattern-reinject without session ID exits silently."""
    monkeypatch.delenv("SCOPE_SESSION_ID", raising=False)

    result = runner.invoke(main, ["pattern-reinject"])

    assert result.exit_code == 0
    assert result.output == ""


def test_pattern_reinject_includes_deviation_reminder(runner, setup_session):
    """Test pattern-reinject includes deviation reminder."""
    save_pattern_state(
        session_id="0",
        pattern="ralph",
        phases=["critique", "improve"],
    )

    result = runner.invoke(main, ["pattern-reinject"])

    assert result.exit_code == 0
    assert "deviate" in result.output.lower()


# --- Commit command tests ---


def test_commit_command(runner, setup_session, monkeypatch):
    """Test scope commit registers pattern."""
    from scope.commands.commit import commit

    result = runner.invoke(commit, ["tdd"])

    assert result.exit_code == 0
    assert "Committed to tdd" in result.output
    assert "red → green → refactor" in result.output

    # Verify state was saved
    state = load_pattern_state("0")
    assert state is not None
    assert state["pattern"] == "tdd"


def test_commit_command_unknown_pattern(runner, setup_session, monkeypatch):
    """Test scope commit rejects unknown patterns."""
    from scope.commands.commit import commit

    result = runner.invoke(commit, ["unknown"])

    assert result.exit_code == 1
    assert "unknown pattern" in result.output.lower()


def test_commit_command_no_session(runner, mock_scope_base, monkeypatch):
    """Test scope commit fails without session."""
    monkeypatch.delenv("SCOPE_SESSION_ID", raising=False)

    from scope.commands.commit import commit

    result = runner.invoke(commit, ["tdd"])

    assert result.exit_code == 1
    assert "not in a scope session" in result.output.lower()


def test_commit_command_case_insensitive(runner, setup_session, monkeypatch):
    """Test scope commit is case-insensitive."""
    from scope.commands.commit import commit

    result = runner.invoke(commit, ["TDD"])

    assert result.exit_code == 0
    state = load_pattern_state("0")
    assert state["pattern"] == "tdd"


# --- Advance command tests ---


def test_advance_command(runner, setup_session, monkeypatch):
    """Test scope advance moves to next phase."""
    from scope.commands.commit import advance

    save_pattern_state(
        session_id="0",
        pattern="tdd",
        phases=["red", "green", "refactor"],
    )

    result = runner.invoke(advance, [])

    assert result.exit_code == 0
    assert "completed red" in result.output.lower()
    assert "green" in result.output.lower()


def test_advance_command_all_done(runner, setup_session, monkeypatch):
    """Test scope advance when all phases complete."""
    from scope.commands.commit import advance

    save_pattern_state(
        session_id="0",
        pattern="tdd",
        phases=["red", "green", "refactor"],
        completed=["red", "green"],
        current="refactor",
    )

    result = runner.invoke(advance, [])

    assert result.exit_code == 0
    assert "complete" in result.output.lower()


def test_advance_command_no_pattern(runner, setup_session, monkeypatch):
    """Test scope advance without pattern committed."""
    from scope.commands.commit import advance

    result = runner.invoke(advance, [])

    assert result.exit_code == 1
    assert "no pattern committed" in result.output.lower()


def test_advance_command_no_session(runner, mock_scope_base, monkeypatch):
    """Test scope advance fails without session."""
    monkeypatch.delenv("SCOPE_SESSION_ID", raising=False)

    from scope.commands.commit import advance

    result = runner.invoke(advance, [])

    assert result.exit_code == 1
    assert "not in a scope session" in result.output.lower()
