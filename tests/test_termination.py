"""Tests for loop termination criteria and evaluation."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from scope.core.contract import generate_contract
from scope.core.termination import (
    TerminationCheck,
    TerminationResult,
    evaluate_termination,
    load_iteration_count,
    load_max_iterations,
    load_termination_criteria,
    run_criterion,
    save_iteration_count,
    save_max_iterations,
    save_termination_criteria,
)


# --- Termination criteria specification (AC1) ---


class TestTerminationCriteriaSpecification:
    """Termination criteria can be specified in the contract or skill."""

    def test_contract_includes_termination_criteria(self):
        """Contract includes termination criteria section."""
        contract = generate_contract(
            prompt="Implement feature",
            termination=["pytest tests/", "ruff check src/"],
        )

        assert "# Termination Criteria" in contract
        assert "- pytest tests/" in contract
        assert "- ruff check src/" in contract
        assert "feedback loop" in contract

    def test_contract_includes_max_iterations(self):
        """Contract includes max iterations bound."""
        contract = generate_contract(
            prompt="Implement feature",
            termination=["pytest tests/"],
            max_iterations=5,
        )

        assert "max 5 iterations" in contract

    def test_contract_no_termination_when_none(self):
        """No termination section when criteria is None."""
        contract = generate_contract(prompt="Do work", termination=None)

        assert "# Termination Criteria" not in contract

    def test_contract_no_termination_when_empty(self):
        """No termination section when criteria is empty."""
        contract = generate_contract(prompt="Do work", termination=[])

        assert "# Termination Criteria" not in contract

    def test_contract_termination_after_verification(self):
        """Termination section comes after verification."""
        contract = generate_contract(
            prompt="Do work",
            verify=["pytest"],
            termination=["pytest tests/"],
        )

        assert contract.index("# Verification") < contract.index(
            "# Termination Criteria"
        )

    def test_contract_full_ordering_with_termination(self):
        """All sections including termination appear in correct order."""
        contract = generate_contract(
            prompt="Implement feature",
            depends_on=["0.0"],
            phase="GREEN",
            parent_intent="Build the auth system",
            prior_results=["Previous research completed."],
            file_scope=["src/auth/"],
            verify=["pytest"],
            termination=["pytest tests/", "ruff check"],
            max_iterations=3,
        )

        deps_idx = contract.index("# Dependencies")
        phase_idx = contract.index("# Phase")
        intent_idx = contract.index("# Parent Intent")
        results_idx = contract.index("# Prior Results")
        task_idx = contract.index("# Task")
        scope_idx = contract.index("# File Scope")
        verify_idx = contract.index("# Verification")
        term_idx = contract.index("# Termination Criteria")

        assert (
            deps_idx
            < phase_idx
            < intent_idx
            < results_idx
            < task_idx
            < scope_idx
            < verify_idx
            < term_idx
        )

    def test_save_and_load_termination_criteria(self, tmp_path):
        """Termination criteria can be saved and loaded from session dir."""
        criteria = ["pytest tests/", "ruff check src/"]
        save_termination_criteria(tmp_path, criteria)

        loaded = load_termination_criteria(tmp_path)
        assert loaded == criteria

    def test_load_termination_criteria_not_set(self, tmp_path):
        """Returns None when no criteria file exists."""
        loaded = load_termination_criteria(tmp_path)
        assert loaded is None

    def test_load_termination_criteria_empty_file(self, tmp_path):
        """Returns None when criteria file is empty."""
        (tmp_path / "termination_criteria").write_text("")
        loaded = load_termination_criteria(tmp_path)
        assert loaded is None


# --- Criteria checking after each iteration (AC2) ---


class TestCriteriaChecking:
    """After each iteration, Scope runs verification and checks against criteria."""

    def test_run_command_criterion_passing(self, tmp_path):
        """A passing command criterion returns passed=True."""
        check = run_criterion("python -c 'exit(0)'", cwd=tmp_path)
        assert check.passed is True
        assert check.criterion == "python -c 'exit(0)'"

    def test_run_command_criterion_failing(self, tmp_path):
        """A failing command criterion returns passed=False."""
        check = run_criterion("python -c 'exit(1)'", cwd=tmp_path)
        assert check.passed is False

    def test_run_command_criterion_with_error_detail(self, tmp_path):
        """A failing command captures error detail."""
        check = run_criterion(
            "python -c 'import sys; print(\"oops\", file=sys.stderr); exit(1)'",
            cwd=tmp_path,
        )
        assert check.passed is False
        assert "oops" in check.detail

    def test_descriptive_criterion_not_auto_verified(self):
        """Descriptive criteria cannot be automatically verified."""
        check = run_criterion("all types pass")
        assert check.passed is False
        assert "descriptive" in check.detail

    def test_evaluate_all_passing(self, tmp_path):
        """All criteria passing produces terminate recommendation."""
        result = evaluate_termination(
            criteria=["python -c 'exit(0)'"],
            iteration=1,
            max_iterations=5,
            cwd=tmp_path,
        )
        assert result.recommend_terminate is True
        assert "all criteria passed" in result.reason

    def test_evaluate_some_failing(self, tmp_path):
        """Some criteria failing produces iterate recommendation."""
        result = evaluate_termination(
            criteria=["python -c 'exit(0)'", "python -c 'exit(1)'"],
            iteration=1,
            max_iterations=5,
            cwd=tmp_path,
        )
        assert result.recommend_terminate is False
        assert "criteria not met" in result.reason

    def test_iteration_counter_persistence(self, tmp_path):
        """Iteration counter can be saved and loaded."""
        assert load_iteration_count(tmp_path) == 0

        save_iteration_count(tmp_path, 3)
        assert load_iteration_count(tmp_path) == 3

        save_iteration_count(tmp_path, 4)
        assert load_iteration_count(tmp_path) == 4


# --- Recommendation messages (AC3) ---


class TestRecommendationMessages:
    """Orchestrator receives explicit recommendation to terminate or iterate."""

    def test_terminate_recommendation_all_pass(self, tmp_path):
        """Criteria met produces 'criteria met, recommend terminate'."""
        result = evaluate_termination(
            criteria=["python -c 'exit(0)'"],
            iteration=1,
            max_iterations=5,
            cwd=tmp_path,
        )
        assert result.recommend_terminate is True
        summary = result.summary()
        assert "TERMINATE" in summary
        assert "all criteria passed" in summary

    def test_iterate_recommendation_criteria_not_met(self, tmp_path):
        """Criteria not met produces 'criteria not met, recommend iterate'."""
        result = evaluate_termination(
            criteria=["python -c 'exit(1)'"],
            iteration=1,
            max_iterations=5,
            cwd=tmp_path,
        )
        assert result.recommend_terminate is False
        summary = result.summary()
        assert "ITERATE" in summary
        assert "criteria not met" in summary

    def test_summary_includes_iteration_info(self, tmp_path):
        """Summary includes iteration count."""
        result = evaluate_termination(
            criteria=["python -c 'exit(0)'"],
            iteration=3,
            max_iterations=5,
            cwd=tmp_path,
        )
        assert "3/5" in result.summary()

    def test_summary_includes_check_results(self, tmp_path):
        """Summary includes individual check results."""
        result = evaluate_termination(
            criteria=["python -c 'exit(0)'", "python -c 'exit(1)'"],
            iteration=1,
            max_iterations=5,
            cwd=tmp_path,
        )
        summary = result.summary()
        assert "[PASS]" in summary
        assert "[FAIL]" in summary

    def test_terminate_at_max_with_failures(self, tmp_path):
        """At max iterations, recommend terminate even with failures."""
        result = evaluate_termination(
            criteria=["python -c 'exit(1)'"],
            iteration=5,
            max_iterations=5,
            cwd=tmp_path,
        )
        assert result.recommend_terminate is True
        assert "max iterations" in result.reason
        summary = result.summary()
        assert "TERMINATE" in summary


# --- Max iteration bounds (AC4) ---


class TestMaxIterationBounds:
    """Max iteration bounds prevent infinite loops."""

    def test_max_iterations_default(self, tmp_path):
        """Default max iterations is 10."""
        assert load_max_iterations(tmp_path) == 10

    def test_max_iterations_save_and_load(self, tmp_path):
        """Max iterations can be saved and loaded."""
        save_max_iterations(tmp_path, 5)
        assert load_max_iterations(tmp_path) == 5

    def test_terminate_at_max_iterations(self, tmp_path):
        """Reaching max iterations recommends terminate regardless."""
        result = evaluate_termination(
            criteria=["python -c 'exit(1)'"],
            iteration=10,
            max_iterations=10,
            cwd=tmp_path,
        )
        assert result.recommend_terminate is True
        assert "max iterations" in result.reason

    def test_does_not_terminate_before_max(self, tmp_path):
        """Before max iterations, failing criteria recommends iterate."""
        result = evaluate_termination(
            criteria=["python -c 'exit(1)'"],
            iteration=9,
            max_iterations=10,
            cwd=tmp_path,
        )
        assert result.recommend_terminate is False

    def test_max_iterations_invalid_file(self, tmp_path):
        """Invalid max_iterations file falls back to default."""
        (tmp_path / "max_iterations").write_text("not a number")
        assert load_max_iterations(tmp_path) == 10

    def test_iteration_count_invalid_file(self, tmp_path):
        """Invalid iteration file falls back to 0."""
        (tmp_path / "iteration").write_text("not a number")
        assert load_iteration_count(tmp_path) == 0


# --- Orchestrator override authority (AC5) ---


class TestOrchestratorOverride:
    """Orchestrator retains authority to override termination recommendations."""

    def test_result_is_recommendation_not_enforcement(self, tmp_path):
        """TerminationResult provides recommendation, not enforcement."""
        result = evaluate_termination(
            criteria=["python -c 'exit(0)'"],
            iteration=1,
            max_iterations=5,
            cwd=tmp_path,
        )
        # The result is a data object — orchestrator decides what to do with it
        assert isinstance(result.recommend_terminate, bool)
        assert isinstance(result.reason, str)
        assert isinstance(result.checks, list)
        # Summary uses "Recommendation:" not "Decision:" or "Action:"
        assert "Recommendation:" in result.summary()

    def test_check_termination_exit_codes(self, mock_scope_base):
        """check-termination command uses exit codes for scripting."""
        from scope.commands.check_termination import check_termination

        runner = CliRunner()

        # Create a session with termination criteria
        session_dir = mock_scope_base / "sessions" / "0"
        session_dir.mkdir(parents=True)
        (session_dir / "task").write_text("test task")
        (session_dir / "state").write_text("running")
        (session_dir / "parent").write_text("")
        (session_dir / "tmux").write_text("scope-0")
        (session_dir / "created_at").write_text("2024-01-01T00:00:00")
        (session_dir / "alias").write_text("")

        save_termination_criteria(session_dir, ["python -c 'exit(0)'"])
        save_max_iterations(session_dir, 5)
        save_iteration_count(session_dir, 1)

        # Exit code 0 = recommend terminate (all pass)
        result = runner.invoke(check_termination, ["0"])
        assert result.exit_code == 0

    def test_check_termination_iterate_exit_code(self, mock_scope_base):
        """check-termination returns exit code 2 for iterate recommendation."""
        from scope.commands.check_termination import check_termination

        runner = CliRunner()

        session_dir = mock_scope_base / "sessions" / "0"
        session_dir.mkdir(parents=True)
        (session_dir / "task").write_text("test task")
        (session_dir / "state").write_text("running")
        (session_dir / "parent").write_text("")
        (session_dir / "tmux").write_text("scope-0")
        (session_dir / "created_at").write_text("2024-01-01T00:00:00")
        (session_dir / "alias").write_text("")

        save_termination_criteria(session_dir, ["python -c 'exit(1)'"])
        save_max_iterations(session_dir, 5)
        save_iteration_count(session_dir, 1)

        # Exit code 2 = recommend iterate (criteria not met)
        result = runner.invoke(check_termination, ["0"])
        assert result.exit_code == 2

    def test_check_termination_increment(self, mock_scope_base):
        """--increment flag advances the iteration counter."""
        from scope.commands.check_termination import check_termination

        runner = CliRunner()

        session_dir = mock_scope_base / "sessions" / "0"
        session_dir.mkdir(parents=True)
        (session_dir / "task").write_text("test task")
        (session_dir / "state").write_text("running")
        (session_dir / "parent").write_text("")
        (session_dir / "tmux").write_text("scope-0")
        (session_dir / "created_at").write_text("2024-01-01T00:00:00")
        (session_dir / "alias").write_text("")

        save_termination_criteria(session_dir, ["python -c 'exit(0)'"])
        save_max_iterations(session_dir, 5)
        save_iteration_count(session_dir, 0)

        runner.invoke(check_termination, ["--increment", "0"])

        assert load_iteration_count(session_dir) == 1

    def test_check_termination_json_output(self, mock_scope_base):
        """--json flag outputs machine-readable JSON."""
        import orjson

        from scope.commands.check_termination import check_termination

        runner = CliRunner()

        session_dir = mock_scope_base / "sessions" / "0"
        session_dir.mkdir(parents=True)
        (session_dir / "task").write_text("test task")
        (session_dir / "state").write_text("running")
        (session_dir / "parent").write_text("")
        (session_dir / "tmux").write_text("scope-0")
        (session_dir / "created_at").write_text("2024-01-01T00:00:00")
        (session_dir / "alias").write_text("")

        save_termination_criteria(session_dir, ["python -c 'exit(0)'"])
        save_max_iterations(session_dir, 5)
        save_iteration_count(session_dir, 1)

        result = runner.invoke(check_termination, ["--json", "0"])
        data = orjson.loads(result.output)

        assert data["session"] == "0"
        assert data["recommend_terminate"] is True
        assert data["iteration"] == 1
        assert data["max_iterations"] == 5
        assert len(data["checks"]) == 1

    def test_check_termination_no_criteria_error(self, mock_scope_base):
        """Error when no termination criteria set."""
        from scope.commands.check_termination import check_termination

        runner = CliRunner()

        session_dir = mock_scope_base / "sessions" / "0"
        session_dir.mkdir(parents=True)
        (session_dir / "task").write_text("test task")
        (session_dir / "state").write_text("running")
        (session_dir / "parent").write_text("")
        (session_dir / "tmux").write_text("scope-0")
        (session_dir / "created_at").write_text("2024-01-01T00:00:00")
        (session_dir / "alias").write_text("")

        result = runner.invoke(check_termination, ["0"])
        assert result.exit_code == 1
        assert "No termination criteria" in result.output


# --- Command heuristic detection ---


class TestCommandDetection:
    """Test the command vs descriptive criterion heuristic."""

    def test_pytest_is_command(self, tmp_path):
        """pytest is detected as a command."""
        check = run_criterion("pytest tests/", cwd=tmp_path)
        # It should attempt to run it (may fail if pytest not found via shell)
        assert check.criterion == "pytest tests/"

    def test_ruff_is_command(self, tmp_path):
        """ruff is detected as a command."""
        check = run_criterion("ruff check src/", cwd=tmp_path)
        assert check.criterion == "ruff check src/"

    def test_natural_language_is_descriptive(self):
        """Natural language is treated as descriptive."""
        check = run_criterion("all tests pass and lint is clean")
        assert check.passed is False
        assert "descriptive" in check.detail

    def test_make_is_command(self, tmp_path):
        """make is detected as a command."""
        check = run_criterion("make test", cwd=tmp_path)
        assert check.criterion == "make test"

    def test_npm_is_command(self, tmp_path):
        """npm is detected as a command."""
        check = run_criterion("npm test", cwd=tmp_path)
        assert check.criterion == "npm test"

    def test_script_path_is_command(self, tmp_path):
        """./script.sh is detected as a command."""
        script = tmp_path / "test.sh"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        check = run_criterion("./test.sh", cwd=tmp_path)
        assert check.passed is True
