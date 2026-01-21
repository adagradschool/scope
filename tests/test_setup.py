"""Tests for scope setup command."""

from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from scope.commands.setup import setup as setup_cmd


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


def test_setup_installs_tk_on_darwin(runner, monkeypatch):
    """Test setup installs tk via brew on macOS when missing."""
    monkeypatch.setattr("scope.commands.setup.tmux_is_installed", lambda: True)
    monkeypatch.setattr("scope.commands.setup.ensure_setup", lambda **_kwargs: None)
    monkeypatch.setattr("scope.commands.setup.platform.system", lambda: "Darwin")
    monkeypatch.setattr("scope.commands.setup.shutil.which", lambda _name: None)

    captured = {}

    def fake_run(args):
        captured["args"] = args
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("scope.commands.setup.subprocess.run", fake_run)

    result = runner.invoke(setup_cmd)
    assert result.exit_code == 0
    assert captured["args"] == ["brew", "install", "ticket"]


def test_setup_no_brew_when_tk_present(runner, monkeypatch):
    """Test setup skips brew install when tk is already present."""
    monkeypatch.setattr("scope.commands.setup.tmux_is_installed", lambda: True)
    monkeypatch.setattr("scope.commands.setup.ensure_setup", lambda **_kwargs: None)
    monkeypatch.setattr("scope.commands.setup.platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "scope.commands.setup.shutil.which", lambda _name: "/opt/homebrew/bin/tk"
    )

    def fake_run(_args):
        raise AssertionError("brew should not be invoked when tk exists")

    monkeypatch.setattr("scope.commands.setup.subprocess.run", fake_run)

    result = runner.invoke(setup_cmd)
    assert result.exit_code == 0
