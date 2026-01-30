"""Tests for the loop engine module."""

from datetime import datetime
from unittest.mock import patch

from scope.core.loop import LoopResult, parse_verdict, run_loop
from scope.core.session import Session


# --- LoopResult dataclass tests ---


def test_loop_result_construction():
    """Test LoopResult can be constructed with required fields."""
    result = LoopResult(
        session_id="0",
        verdict="accept",
        iterations=1,
    )
    assert result.session_id == "0"
    assert result.verdict == "accept"
    assert result.iterations == 1
    assert result.history == []
    assert result.result_text == ""
    assert result.exit_reason == ""


def test_loop_result_all_fields():
    """Test LoopResult with all fields populated."""
    history = [{"iteration": 0, "verdict": "retry", "feedback": "try again"}]
    result = LoopResult(
        session_id="1",
        verdict="max_iterations",
        iterations=3,
        history=history,
        result_text="some output",
        exit_reason="agent decided to stop",
    )
    assert result.session_id == "1"
    assert result.verdict == "max_iterations"
    assert result.iterations == 3
    assert result.history == history
    assert result.result_text == "some output"
    assert result.exit_reason == "agent decided to stop"


def test_loop_result_exit_verdict():
    """Test LoopResult with exit verdict and reason."""
    result = LoopResult(
        session_id="2",
        verdict="exit",
        iterations=1,
        exit_reason="Auth module uses event-driven pattern, need to redesign",
    )
    assert result.verdict == "exit"
    assert (
        result.exit_reason == "Auth module uses event-driven pattern, need to redesign"
    )


def test_loop_result_history_default_mutable():
    """Test that each LoopResult gets its own history list."""
    r1 = LoopResult(session_id="a", verdict="accept", iterations=1)
    r2 = LoopResult(session_id="b", verdict="accept", iterations=1)
    r1.history.append({"iteration": 0})
    assert r2.history == []


# --- parse_verdict tests (moved from test_spawn.py) ---


def test_parse_verdict_accept():
    """Test parsing ACCEPT verdict."""
    verdict, feedback = parse_verdict("The code looks good.\n\nACCEPT")
    assert verdict == "accept"
    assert "code looks good" in feedback


def test_parse_verdict_retry():
    """Test parsing RETRY verdict."""
    verdict, feedback = parse_verdict("Missing error handling.\n\nRETRY")
    assert verdict == "retry"
    assert "Missing error handling" in feedback


def test_parse_verdict_terminate():
    """Test parsing TERMINATE verdict."""
    verdict, feedback = parse_verdict("The task is impossible.\n\nTERMINATE")
    assert verdict == "terminate"


def test_parse_verdict_case_insensitive():
    """Test verdict parsing is case insensitive."""
    verdict, _ = parse_verdict("Looks great!\n\naccept")
    assert verdict == "accept"


def test_parse_verdict_no_verdict_defaults_retry():
    """Test that missing verdict defaults to retry."""
    verdict, feedback = parse_verdict("Some feedback without a verdict")
    assert verdict == "retry"
    assert "Some feedback without a verdict" in feedback


def test_parse_verdict_terminate_priority():
    """Test TERMINATE takes priority when scanning from end."""
    verdict, _ = parse_verdict("ACCEPT this but also TERMINATE")
    assert verdict == "terminate"


def test_parse_verdict_last_line_wins():
    """Test the last verdict line wins."""
    verdict, _ = parse_verdict("RETRY\nACCEPT")
    assert verdict == "accept"


# --- run_loop exit detection tests ---


@patch("scope.core.loop.wait_for_sessions")
@patch("scope.core.loop.read_result")
@patch("scope.core.loop.load_session")
@patch("scope.core.loop.load_exit_reason")
@patch("scope.core.loop.ensure_scope_dir")
def test_run_loop_returns_exit_verdict_when_session_exited(
    mock_ensure, mock_load_exit, mock_load_session, mock_read_result, mock_wait
):
    """Test that run_loop returns LoopResult with verdict='exit' when session state is 'exited'."""
    mock_ensure.return_value = "/tmp/fake"
    mock_wait.return_value = None
    mock_read_result.return_value = "some output"
    mock_load_session.return_value = Session(
        id="0",
        task="test task",
        parent="",
        state="exited",
        tmux_session="scope",
        created_at=datetime.now(),
    )
    mock_load_exit.return_value = "Auth module needs redesign"

    result = run_loop(
        session_id="0",
        prompt="test",
        checker="true",
        max_iterations=3,
        checker_model="",
        dangerously_skip_permissions=False,
    )

    assert result.verdict == "exit"
    assert result.exit_reason == "Auth module needs redesign"
    assert result.session_id == "0"
    assert result.iterations == 1
    mock_load_exit.assert_called_once_with("0")


@patch("scope.core.loop.wait_for_sessions")
@patch("scope.core.loop.read_result")
@patch("scope.core.loop.load_session")
@patch("scope.core.loop.load_exit_reason")
@patch("scope.core.loop.ensure_scope_dir")
def test_run_loop_exit_with_no_reason(
    mock_ensure, mock_load_exit, mock_load_session, mock_read_result, mock_wait
):
    """Test that run_loop handles exited state with no exit_reason file gracefully."""
    mock_ensure.return_value = "/tmp/fake"
    mock_wait.return_value = None
    mock_read_result.return_value = ""
    mock_load_session.return_value = Session(
        id="0",
        task="test task",
        parent="",
        state="exited",
        tmux_session="scope",
        created_at=datetime.now(),
    )
    mock_load_exit.return_value = None

    result = run_loop(
        session_id="0",
        prompt="test",
        checker="true",
        max_iterations=3,
        checker_model="",
        dangerously_skip_permissions=False,
    )

    assert result.verdict == "exit"
    assert result.exit_reason == ""
