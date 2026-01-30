"""Tests for workflow CLI command."""

import pytest
from click.testing import CliRunner

from scope.cli import main


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_workflow_help(runner):
    """Help output includes command description."""
    result = runner.invoke(main, ["workflow", "--help"])
    assert result.exit_code == 0
    assert "Run a Python workflow file" in result.output


def test_workflow_missing_file(runner):
    """Missing file argument prints an error."""
    result = runner.invoke(main, ["workflow", "nonexistent.py"])
    assert result.exit_code != 0


def test_workflow_loads_valid_file(runner, tmp_path):
    """A valid Python file is loaded and executed."""
    wf_file = tmp_path / "hello_wf.py"
    wf_file.write_text("import sys; print('workflow-executed')\n")

    result = runner.invoke(main, ["workflow", str(wf_file)])
    assert result.exit_code == 0
    assert "workflow-executed" in result.output


def test_workflow_execution_error(runner, tmp_path):
    """A file that raises an exception reports an error."""
    wf_file = tmp_path / "bad_wf.py"
    wf_file.write_text("raise RuntimeError('boom')\n")

    result = runner.invoke(main, ["workflow", str(wf_file)])
    assert result.exit_code != 0
