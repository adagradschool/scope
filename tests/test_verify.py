"""Tests for verification infrastructure."""

from pathlib import Path
from unittest.mock import patch

import orjson

from scope.core.verify import VerifyStep, run_verification


def test_run_verification_all_pass(tmp_path: Path):
    """Test verification with all steps passing."""
    steps = [
        VerifyStep(name="tests", command="true"),
        VerifyStep(name="lint", command="true"),
    ]
    result = run_verification(steps, cwd=tmp_path)

    assert result.passed is True
    assert len(result.steps) == 2
    assert result.steps[0].name == "tests"
    assert result.steps[0].passed is True
    assert result.steps[1].name == "lint"
    assert result.steps[1].passed is True
    assert "tests passed" in result.summary
    assert "lint passed" in result.summary


def test_run_verification_one_fails(tmp_path: Path):
    """Test verification with one step failing."""
    steps = [
        VerifyStep(name="tests", command="true"),
        VerifyStep(name="lint", command="false"),
    ]
    result = run_verification(steps, cwd=tmp_path)

    assert result.passed is False
    assert result.steps[0].passed is True
    assert result.steps[1].passed is False
    assert "tests passed" in result.summary
    assert "lint FAILED" in result.summary


def test_run_verification_captures_stdout(tmp_path: Path):
    """Test that stdout is captured."""
    steps = [VerifyStep(name="echo", command="echo hello world")]
    result = run_verification(steps, cwd=tmp_path)

    assert result.passed is True
    assert "hello world" in result.steps[0].output


def test_run_verification_captures_stderr(tmp_path: Path):
    """Test that stderr is captured."""
    steps = [VerifyStep(name="err", command="echo oops >&2")]
    result = run_verification(steps, cwd=tmp_path)

    assert "oops" in result.steps[0].output


def test_run_verification_timeout(tmp_path: Path):
    """Test that commands time out."""
    steps = [VerifyStep(name="slow", command="sleep 10")]
    result = run_verification(steps, cwd=tmp_path, timeout=1)

    assert result.passed is False
    assert result.steps[0].passed is False
    assert "timed out" in result.steps[0].output


def test_run_verification_empty_steps(tmp_path: Path):
    """Test verification with no steps."""
    result = run_verification([], cwd=tmp_path)

    assert result.passed is True
    assert len(result.steps) == 0
    assert result.summary == ""


def test_run_verification_uses_cwd(tmp_path: Path):
    """Test that commands run in the specified directory."""
    steps = [VerifyStep(name="pwd", command="pwd")]
    result = run_verification(steps, cwd=tmp_path)

    assert result.passed is True
    assert str(tmp_path) in result.steps[0].output


def test_run_verification_nonexistent_command(tmp_path: Path):
    """Test handling of commands that don't exist."""
    steps = [VerifyStep(name="bad", command="nonexistent_command_xyz_123")]
    result = run_verification(steps, cwd=tmp_path)

    assert result.passed is False
    assert result.steps[0].passed is False


def test_run_verification_exit_code(tmp_path: Path):
    """Test that non-zero exit codes are treated as failures."""
    steps = [VerifyStep(name="fail", command="exit 42")]
    result = run_verification(steps, cwd=tmp_path)

    assert result.passed is False
    assert result.steps[0].passed is False


def test_run_verification_summary_format(tmp_path: Path):
    """Test summary string format."""
    steps = [
        VerifyStep(name="tests", command="true"),
        VerifyStep(name="lint", command="false"),
        VerifyStep(name="types", command="true"),
    ]
    result = run_verification(steps, cwd=tmp_path)

    assert result.summary == "tests passed, lint FAILED, types passed"


# --- Handler integration tests ---


def test_stop_hook_runs_verification(tmp_path: Path):
    """Test that the stop hook runs verification when verify.json exists."""
    from scope.hooks.handler import _run_session_verification

    # Create verify config
    verify_config = [
        {"name": "check", "command": "echo all good"},
    ]
    verify_file = tmp_path / "verify.json"
    verify_file.write_bytes(orjson.dumps(verify_config))

    _run_session_verification(tmp_path, verify_file)

    # Check result was written
    result_file = tmp_path / "verify_result.json"
    assert result_file.exists()
    data = orjson.loads(result_file.read_bytes())
    assert data["passed"] is True
    assert len(data["steps"]) == 1
    assert data["steps"][0]["name"] == "check"
    assert data["steps"][0]["passed"] is True


def test_stop_hook_verification_with_failure(tmp_path: Path):
    """Test stop hook verification captures failures."""
    from scope.hooks.handler import _run_session_verification

    verify_config = [
        {"name": "pass", "command": "true"},
        {"name": "fail", "command": "false"},
    ]
    verify_file = tmp_path / "verify.json"
    verify_file.write_bytes(orjson.dumps(verify_config))

    _run_session_verification(tmp_path, verify_file)

    result_file = tmp_path / "verify_result.json"
    data = orjson.loads(result_file.read_bytes())
    assert data["passed"] is False
    assert data["steps"][0]["passed"] is True
    assert data["steps"][1]["passed"] is False


def test_stop_hook_invalid_verify_json(tmp_path: Path):
    """Test stop hook handles invalid verify.json gracefully."""
    from scope.hooks.handler import _run_session_verification

    verify_file = tmp_path / "verify.json"
    verify_file.write_text("not valid json{{{")

    _run_session_verification(tmp_path, verify_file)

    # Should not create result file
    result_file = tmp_path / "verify_result.json"
    assert not result_file.exists()


def test_stop_hook_empty_verify_steps(tmp_path: Path):
    """Test stop hook handles empty steps list."""
    from scope.hooks.handler import _run_session_verification

    verify_file = tmp_path / "verify.json"
    verify_file.write_bytes(orjson.dumps([]))

    _run_session_verification(tmp_path, verify_file)

    # Should not create result file for empty steps
    result_file = tmp_path / "verify_result.json"
    assert not result_file.exists()


# --- Wait output tests ---


def test_wait_output_verification(tmp_path: Path):
    """Test that _output_verification formats results correctly."""
    from click.testing import CliRunner
    from scope.commands.wait import _output_verification

    data = {
        "passed": True,
        "summary": "tests passed, lint passed",
        "steps": [
            {"name": "tests", "passed": True, "output": ""},
            {"name": "lint", "passed": True, "output": ""},
        ],
    }
    verify_file = tmp_path / "verify_result.json"
    verify_file.write_bytes(orjson.dumps(data))

    runner = CliRunner()
    with runner.isolated_filesystem():
        # Capture click output
        import io
        output = io.StringIO()
        with patch("click.echo", side_effect=lambda msg, **kw: output.write(str(msg) + "\n")):
            _output_verification(verify_file)

    result = output.getvalue()
    assert "Verification:" in result
    assert "tests passed" in result
    assert "lint passed" in result


def test_wait_output_verification_with_failure(tmp_path: Path):
    """Test verification output with failures."""
    from scope.commands.wait import _output_verification

    data = {
        "passed": False,
        "summary": "tests FAILED, lint passed",
        "steps": [
            {"name": "tests", "passed": False, "output": "3 failures"},
            {"name": "lint", "passed": True, "output": ""},
        ],
    }
    verify_file = tmp_path / "verify_result.json"
    verify_file.write_bytes(orjson.dumps(data))

    import io
    output = io.StringIO()
    with patch("click.echo", side_effect=lambda msg, **kw: output.write(str(msg) + "\n")):
        _output_verification(verify_file)

    result = output.getvalue()
    assert "tests FAILED" in result
    assert "lint passed" in result
