"""Tests for scope setup command."""

import pytest
from click.testing import CliRunner

from scope.commands.setup import setup as setup_cmd


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_setup_runs_install(runner, monkeypatch):
    """Test setup runs ensure_setup when tmux is installed."""
    monkeypatch.setattr("scope.commands.setup.tmux_is_installed", lambda: True)
    monkeypatch.setattr("scope.commands.setup.platform.system", lambda: "Darwin")

    called = {"count": 0}

    def fake_ensure_setup(**_kwargs):
        called["count"] += 1

    monkeypatch.setattr("scope.commands.setup.ensure_setup", fake_ensure_setup)

    result = runner.invoke(setup_cmd)
    assert result.exit_code == 0
    assert called["count"] == 1


def test_setup_errors_when_tmux_missing(runner, monkeypatch):
    """Test setup errors when tmux is not installed."""
    monkeypatch.setattr("scope.commands.setup.tmux_is_installed", lambda: False)
    monkeypatch.setattr("scope.commands.setup.platform.system", lambda: "Linux")

    result = runner.invoke(setup_cmd)
    assert result.exit_code == 1
