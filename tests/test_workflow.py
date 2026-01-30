"""Tests for the Workflow builder API and run() execution."""

import subprocess
from datetime import datetime, timezone
from unittest.mock import patch

import orjson
import pytest

from scope.core.loop import LoopResult
from scope.core.session import Session
from scope.workflow import (
    Phase,
    PhaseResult,
    Workflow,
    _build_phase_task,
    _collect_prior_results,
    _read_loop_result,
)


# ---------------------------------------------------------------------------
# Workflow creation
# ---------------------------------------------------------------------------


def test_workflow_creation():
    """Workflow stores name and starts with empty phases."""
    wf = Workflow("tdd")
    assert wf.name == "tdd"
    assert wf.phases == []
    assert wf._phase_names == set()


# ---------------------------------------------------------------------------
# Phase registration
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Pipe validation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# All options
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# PhaseResult properties
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _build_phase_task
# ---------------------------------------------------------------------------


def test_build_phase_task_simple():
    """Task prompt is the phase task when no extras are set."""
    phase = Phase(name="a", task="Do the thing", checker="true")
    result = _build_phase_task(phase, 0, [phase], {})
    assert result == "Do the thing"


def test_build_phase_task_with_file_scope():
    """File scope is appended to the task prompt."""
    phase = Phase(
        name="a",
        task="Fix auth",
        checker="true",
        file_scope=["src/auth.py", "tests/test_auth.py"],
    )
    result = _build_phase_task(phase, 0, [phase], {})
    assert "# File Scope" in result
    assert "- `src/auth.py`" in result
    assert "- `tests/test_auth.py`" in result


def test_build_phase_task_with_verify():
    """Verify commands are appended to the task prompt."""
    phase = Phase(
        name="a",
        task="Fix auth",
        checker="true",
        verify=["pytest tests/", "ruff check src/"],
    )
    result = _build_phase_task(phase, 0, [phase], {})
    assert "# Verification" in result
    assert "- pytest tests/" in result
    assert "- ruff check src/" in result


def test_build_phase_task_with_prior_results():
    """Prior results from preceding phase are included."""
    phase_a = Phase(name="a", task="Do A", checker="true")
    phase_b = Phase(name="b", task="Do B", checker="true")

    lr = LoopResult(session_id="0", verdict="accept", iterations=1, result_text="A done")
    results = {"a": PhaseResult(phase_name="a", loop_result=lr, passed=True)}

    task = _build_phase_task(phase_b, 1, [phase_a, phase_b], results)
    assert "# Prior Phase Results" in task
    assert "**a**: A done" in task


def test_build_phase_task_with_pipe_from():
    """Explicit pipe_from overrides default predecessor piping."""
    phase_a = Phase(name="a", task="Do A", checker="true")
    phase_b = Phase(name="b", task="Do B", checker="true")
    phase_c = Phase(name="c", task="Do C", checker="true", pipe_from=["a"])

    lr_a = LoopResult(session_id="0", verdict="accept", iterations=1, result_text="A result")
    lr_b = LoopResult(session_id="1", verdict="accept", iterations=1, result_text="B result")
    results = {
        "a": PhaseResult(phase_name="a", loop_result=lr_a, passed=True),
        "b": PhaseResult(phase_name="b", loop_result=lr_b, passed=True),
    }

    task = _build_phase_task(phase_c, 2, [phase_a, phase_b, phase_c], results)
    assert "**a**: A result" in task
    assert "B result" not in task


# ---------------------------------------------------------------------------
# _collect_prior_results
# ---------------------------------------------------------------------------


def test_collect_prior_results_default_pipes_from_predecessor():
    """Without pipe_from, pipes from the immediately preceding phase."""
    phase_a = Phase(name="a", task="A", checker="true")
    phase_b = Phase(name="b", task="B", checker="true")

    lr = LoopResult(session_id="0", verdict="accept", iterations=1, result_text="done")
    results = {"a": PhaseResult(phase_name="a", loop_result=lr, passed=True)}

    prior = _collect_prior_results(phase_b, 1, [phase_a, phase_b], results)
    assert len(prior) == 1
    assert "**a**:" in prior[0]


def test_collect_prior_results_first_phase_empty():
    """First phase has no prior results."""
    phase = Phase(name="a", task="A", checker="true")
    prior = _collect_prior_results(phase, 0, [phase], {})
    assert prior == []


def test_collect_prior_results_empty_result_text_skipped():
    """Phases with empty result_text are not included."""
    phase_a = Phase(name="a", task="A", checker="true")
    phase_b = Phase(name="b", task="B", checker="true")

    lr = LoopResult(session_id="0", verdict="accept", iterations=1, result_text="")
    results = {"a": PhaseResult(phase_name="a", loop_result=lr, passed=True)}

    prior = _collect_prior_results(phase_b, 1, [phase_a, phase_b], results)
    assert prior == []


def test_collect_prior_results_explicit_pipe_from_multiple():
    """pipe_from collects from multiple named phases."""
    phase_a = Phase(name="a", task="A", checker="true")
    phase_b = Phase(name="b", task="B", checker="true")
    phase_c = Phase(name="c", task="C", checker="true", pipe_from=["a", "b"])

    lr_a = LoopResult(session_id="0", verdict="accept", iterations=1, result_text="A out")
    lr_b = LoopResult(session_id="1", verdict="accept", iterations=1, result_text="B out")
    results = {
        "a": PhaseResult(phase_name="a", loop_result=lr_a, passed=True),
        "b": PhaseResult(phase_name="b", loop_result=lr_b, passed=True),
    }

    prior = _collect_prior_results(phase_c, 2, [phase_a, phase_b, phase_c], results)
    assert len(prior) == 2
    assert "**a**: A out" in prior[0]
    assert "**b**: B out" in prior[1]


# ---------------------------------------------------------------------------
# _read_loop_result
# ---------------------------------------------------------------------------


def test_read_loop_result_empty_session_id():
    """Empty session ID returns a terminate result."""
    phase = Phase(name="a", task="A", checker="true")
    lr = _read_loop_result("", phase)
    assert lr.verdict == "terminate"
    assert lr.iterations == 0


def test_read_loop_result_accept(tmp_path, monkeypatch):
    """Reads loop state with accept verdict."""
    _setup_session_dir(tmp_path, "42", state="done", result="all good", history=[
        {"iteration": 0, "doer_session": "42", "verdict": "accept", "feedback": "ok"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)

    phase = Phase(name="a", task="A", checker="true")
    lr = _read_loop_result("42", phase)
    assert lr.verdict == "accept"
    assert lr.result_text == "all good"
    assert lr.session_id == "42"
    assert lr.iterations == 1


def test_read_loop_result_max_iterations(tmp_path, monkeypatch):
    """Retry in last history entry means max_iterations was reached."""
    _setup_session_dir(tmp_path, "42", state="done", result="partial", history=[
        {"iteration": 0, "doer_session": "42", "verdict": "retry", "feedback": "nope"},
        {"iteration": 1, "doer_session": "42.0", "verdict": "retry", "feedback": "still nope"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)

    phase = Phase(name="a", task="A", checker="true", max_iterations=2)
    lr = _read_loop_result("42", phase)
    assert lr.verdict == "max_iterations"
    assert lr.iterations == 2


def test_read_loop_result_terminate(tmp_path, monkeypatch):
    """Terminate verdict from checker."""
    _setup_session_dir(tmp_path, "42", state="done", result="", history=[
        {"iteration": 0, "doer_session": "42", "verdict": "terminate", "feedback": "broken"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)

    phase = Phase(name="a", task="A", checker="true")
    lr = _read_loop_result("42", phase)
    assert lr.verdict == "terminate"


def test_read_loop_result_exited(tmp_path, monkeypatch):
    """Session that exited returns exit verdict with reason."""
    _setup_session_dir(
        tmp_path, "42", state="exited", result="",
        history=[], exit_reason="needs redesign",
    )
    _patch_state_funcs(monkeypatch, tmp_path)

    phase = Phase(name="a", task="A", checker="true")
    lr = _read_loop_result("42", phase)
    assert lr.verdict == "exit"
    assert lr.exit_reason == "needs redesign"


def test_read_loop_result_aborted(tmp_path, monkeypatch):
    """Aborted session returns terminate verdict."""
    _setup_session_dir(tmp_path, "42", state="aborted", result="", history=[])
    _patch_state_funcs(monkeypatch, tmp_path)

    phase = Phase(name="a", task="A", checker="true")
    lr = _read_loop_result("42", phase)
    assert lr.verdict == "terminate"


def test_read_loop_result_no_history(tmp_path, monkeypatch):
    """No loop history defaults to max_iterations."""
    _setup_session_dir(tmp_path, "42", state="done", result="ok", history=[])
    _patch_state_funcs(monkeypatch, tmp_path)

    phase = Phase(name="a", task="A", checker="true")
    lr = _read_loop_result("42", phase)
    assert lr.verdict == "max_iterations"


# ---------------------------------------------------------------------------
# Workflow.run() — integration tests with mocked subprocess
# ---------------------------------------------------------------------------


def test_run_empty_workflow():
    """Empty workflow returns empty dict."""
    wf = Workflow("empty")
    assert wf.run() == {}


def test_run_single_phase_accept(tmp_path, monkeypatch):
    """Single phase that accepts produces a passing result."""
    _setup_session_dir(tmp_path, "0", state="done", result="built it", history=[
        {"iteration": 0, "doer_session": "0", "verdict": "accept", "feedback": "good"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)
    _patch_subprocess(monkeypatch, stdout="0\n")

    wf = Workflow("test")
    wf.phase("build", task="Build it", checker="make check")
    results = wf.run()

    assert "build" in results
    assert results["build"].passed is True
    assert results["build"].verdict == "accept"
    assert results["build"].result_text == "built it"


def test_run_single_phase_failure_stops(tmp_path, monkeypatch):
    """Single failing phase with on_fail=stop returns failure."""
    _setup_session_dir(tmp_path, "0", state="done", result="bad", history=[
        {"iteration": 0, "doer_session": "0", "verdict": "retry", "feedback": "bad"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)
    _patch_subprocess(monkeypatch, stdout="0\n")

    wf = Workflow("test")
    wf.phase("build", task="Build it", checker="make check")
    results = wf.run()

    assert results["build"].passed is False
    assert results["build"].verdict == "max_iterations"


def test_run_multi_phase_stops_on_failure(tmp_path, monkeypatch):
    """With on_fail=stop (default), workflow stops at first failure."""
    _setup_session_dir(tmp_path, "0", state="done", result="", history=[
        {"iteration": 0, "doer_session": "0", "verdict": "retry", "feedback": "fail"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)
    _patch_subprocess(monkeypatch, stdout="0\n")

    wf = Workflow("test")
    wf.phase("a", task="A", checker="true")
    wf.phase("b", task="B", checker="true")
    results = wf.run()

    assert "a" in results
    assert results["a"].passed is False
    # Phase b was never executed
    assert "b" not in results


def test_run_multi_phase_continue_on_failure(tmp_path, monkeypatch):
    """With on_fail=continue, workflow proceeds past failure."""
    call_count = [0]

    def mock_run(cmd, **kwargs):
        call_count[0] += 1
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="0\n", stderr="")

    monkeypatch.setattr("scope.workflow.subprocess.run", mock_run)

    # Both phases read same session dir — both fail
    _setup_session_dir(tmp_path, "0", state="done", result="partial", history=[
        {"iteration": 0, "doer_session": "0", "verdict": "retry", "feedback": "nope"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)

    wf = Workflow("test")
    wf.phase("a", task="A", checker="true", on_fail="continue")
    wf.phase("b", task="B", checker="true")
    results = wf.run()

    assert "a" in results
    assert "b" in results
    assert results["a"].passed is False
    assert results["b"].passed is False
    assert call_count[0] == 2


def test_run_pipes_results_between_phases(tmp_path, monkeypatch):
    """The second phase receives the first phase's result in its task."""
    captured_cmds = []

    def mock_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="0\n", stderr="")

    monkeypatch.setattr("scope.workflow.subprocess.run", mock_run)
    _setup_session_dir(tmp_path, "0", state="done", result="first phase output", history=[
        {"iteration": 0, "doer_session": "0", "verdict": "accept", "feedback": "ok"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)

    wf = Workflow("pipe")
    wf.phase("a", task="Do A", checker="true")
    wf.phase("b", task="Do B", checker="true")
    wf.run()

    # Second spawn should include prior result in the task prompt
    assert len(captured_cmds) == 2
    second_task = captured_cmds[1][2]  # "scope", "spawn", <task>, ...
    assert "Prior Phase Results" in second_task
    assert "first phase output" in second_task


def test_run_exit_stops_workflow(tmp_path, monkeypatch):
    """Phase with exit verdict stops the workflow."""
    _setup_session_dir(
        tmp_path, "0", state="exited", result="",
        history=[], exit_reason="wrong approach",
    )
    _patch_state_funcs(monkeypatch, tmp_path)
    _patch_subprocess(monkeypatch, stdout="0\n")

    wf = Workflow("test")
    wf.phase("a", task="A", checker="true")
    wf.phase("b", task="B", checker="true")
    results = wf.run()

    assert "a" in results
    assert results["a"].verdict == "exit"
    assert results["a"].exit_reason == "wrong approach"
    assert results["a"].passed is False
    assert "b" not in results


def test_run_passes_model_and_checker_model(tmp_path, monkeypatch):
    """Model and checker_model are passed to scope spawn."""
    captured_cmds = []

    def mock_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="0\n", stderr="")

    monkeypatch.setattr("scope.workflow.subprocess.run", mock_run)
    _setup_session_dir(tmp_path, "0", state="done", result="ok", history=[
        {"iteration": 0, "doer_session": "0", "verdict": "accept", "feedback": "ok"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)

    wf = Workflow("test")
    wf.phase("a", task="Do A", checker="true", model="opus", checker_model="haiku")
    wf.run()

    cmd = captured_cmds[0]
    assert "--model" in cmd
    assert "opus" in cmd
    assert "--checker-model" in cmd
    assert "haiku" in cmd


def test_run_spawn_failure_returns_terminate(monkeypatch):
    """If scope spawn produces no output, result is terminate."""
    _patch_subprocess(monkeypatch, stdout="", returncode=1)

    wf = Workflow("test")
    wf.phase("a", task="A", checker="true")
    results = wf.run()

    assert results["a"].passed is False
    assert results["a"].verdict == "terminate"


def test_run_sets_phase_result_on_phase_object(tmp_path, monkeypatch):
    """run() stores PhaseResult on the Phase.result attribute."""
    _setup_session_dir(tmp_path, "0", state="done", result="ok", history=[
        {"iteration": 0, "doer_session": "0", "verdict": "accept", "feedback": "ok"},
    ])
    _patch_state_funcs(monkeypatch, tmp_path)
    _patch_subprocess(monkeypatch, stdout="0\n")

    wf = Workflow("test")
    wf.phase("a", task="A", checker="true")
    wf.run()

    assert wf.phases[0].result is not None
    assert wf.phases[0].result.passed is True


# ---------------------------------------------------------------------------
# Helpers for mocking
# ---------------------------------------------------------------------------


def _setup_session_dir(
    tmp_path,
    session_id,
    *,
    state="done",
    result="",
    history=None,
    exit_reason=None,
):
    """Create a fake session directory with state files."""
    session_dir = tmp_path / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "state").write_text(state)
    (session_dir / "task").write_text("test task")
    (session_dir / "parent").write_text("")
    (session_dir / "tmux").write_text(f"scope-{session_id}")
    (session_dir / "created_at").write_text(datetime.now(timezone.utc).isoformat())
    (session_dir / "alias").write_text("")
    if result:
        (session_dir / "result").write_text(result)
    if history is not None:
        loop_state = {
            "checker": "true",
            "max_iterations": 3,
            "current_iteration": len(history) - 1 if history else 0,
            "history": history,
        }
        (session_dir / "loop_state.json").write_bytes(orjson.dumps(loop_state))
    if exit_reason is not None:
        (session_dir / "exit_reason").write_text(exit_reason)


def _patch_state_funcs(monkeypatch, tmp_path):
    """Patch state functions to use tmp_path as scope dir."""
    # _read_loop_result imports from scope.core.state at call time
    monkeypatch.setattr(
        "scope.core.state.ensure_scope_dir", lambda: tmp_path
    )
    monkeypatch.setattr(
        "scope.core.state._get_scope_dir", lambda: tmp_path
    )
    monkeypatch.setattr(
        "scope.core.state.get_global_scope_base", lambda: tmp_path
    )


def _patch_subprocess(monkeypatch, *, stdout="0\n", returncode=0):
    """Patch subprocess.run for scope spawn calls."""
    monkeypatch.setattr(
        "scope.workflow.subprocess.run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            args=cmd, returncode=returncode, stdout=stdout, stderr="",
        ),
    )
