"""Tests for the Workflow builder API."""

import pytest

from scope.core.loop import LoopResult
from scope.workflow import Phase, PhaseResult, Workflow


# --- Workflow creation ---


def test_workflow_creation():
    """Workflow stores name and starts with empty phases."""
    wf = Workflow("tdd")
    assert wf.name == "tdd"
    assert wf.phases == []
    assert wf._phase_names == set()


# --- Phase registration ---


def test_phase_registration():
    """Workflow registers phases in order."""
    wf = Workflow("test")
    p1 = wf.phase("red", task="write tests", checker="pytest")
    p2 = wf.phase("green", task="make pass", checker="pytest")

    assert len(wf.phases) == 2
    assert wf.phases[0].name == "red"
    assert wf.phases[1].name == "green"
    assert isinstance(p1, Phase)
    assert isinstance(p2, Phase)


def test_phase_defaults():
    """Phase has sensible defaults."""
    wf = Workflow("test")
    p = wf.phase("build", task="build it", checker="make check")

    assert p.max_iterations == 3
    assert p.checker_model == ""
    assert p.model == ""
    assert p.on_fail == "stop"
    assert p.pipe_from == []
    assert p.file_scope is None
    assert p.verify is None
    assert p.result is None


def test_multiple_phases():
    """Multiple phases are registered and accessible."""
    wf = Workflow("pipeline")
    wf.phase("a", task="do a", checker="true")
    wf.phase("b", task="do b", checker="true")
    wf.phase("c", task="do c", checker="true")

    assert len(wf.phases) == 3
    assert {p.name for p in wf.phases} == {"a", "b", "c"}
    assert wf._phase_names == {"a", "b", "c"}


def test_phase_duplicate_name_raises():
    """Registering a phase with a duplicate name raises ValueError."""
    wf = Workflow("test")
    wf.phase("red", task="write tests", checker="pytest")

    with pytest.raises(ValueError, match="Duplicate phase name"):
        wf.phase("red", task="write more tests", checker="pytest")


# --- Pipe validation ---


def test_pipe_from_valid():
    """Explicit pipe_from references are validated at registration time."""
    wf = Workflow("test")
    wf.phase("red", task="write tests", checker="pytest")
    p = wf.phase("green", task="make pass", checker="pytest", pipe_from=["red"])

    assert p.pipe_from == ["red"]


def test_pipe_from_invalid_raises():
    """Piping from a nonexistent phase raises ValueError."""
    wf = Workflow("test")

    with pytest.raises(ValueError, match="unknown phase"):
        wf.phase("green", task="make pass", checker="pytest", pipe_from=["red"])


# --- All options ---


def test_all_options():
    """Phase accepts all optional parameters."""
    wf = Workflow("test")
    wf.phase("first", task="setup", checker="true")
    p = wf.phase(
        "full",
        task="do everything",
        checker="agent: Review. ACCEPT/RETRY",
        max_iterations=5,
        checker_model="sonnet",
        model="opus",
        on_fail="continue",
        pipe_from=["first"],
        file_scope=["src/auth.py", "tests/test_auth.py"],
        verify=["pytest tests/", "mypy src/"],
    )

    assert p.name == "full"
    assert p.task == "do everything"
    assert p.checker == "agent: Review. ACCEPT/RETRY"
    assert p.max_iterations == 5
    assert p.checker_model == "sonnet"
    assert p.model == "opus"
    assert p.on_fail == "continue"
    assert p.pipe_from == ["first"]
    assert p.file_scope == ["src/auth.py", "tests/test_auth.py"]
    assert p.verify == ["pytest tests/", "mypy src/"]


# --- run() raises NotImplementedError ---


def test_run_raises_not_implemented():
    """Workflow.run() raises NotImplementedError."""
    wf = Workflow("test")
    wf.phase("build", task="build it", checker="make check")

    with pytest.raises(NotImplementedError, match="spawn integration"):
        wf.run()


# --- PhaseResult properties ---


def test_phase_result_properties():
    """PhaseResult exposes result_text, verdict, exit_reason from LoopResult."""
    lr = LoopResult(
        session_id="0",
        verdict="accept",
        iterations=1,
        result_text="all good",
        exit_reason="",
    )
    pr = PhaseResult(phase_name="build", loop_result=lr, passed=True)

    assert pr.result_text == "all good"
    assert pr.verdict == "accept"
    assert pr.exit_reason == ""
    assert pr.passed is True


def test_phase_result_exit():
    """PhaseResult with exit verdict exposes reason."""
    lr = LoopResult(
        session_id="0",
        verdict="exit",
        iterations=1,
        exit_reason="needs redesign",
    )
    pr = PhaseResult(phase_name="build", loop_result=lr, passed=False)

    assert pr.verdict == "exit"
    assert pr.exit_reason == "needs redesign"
    assert pr.passed is False
