"""Tests for the uninstall command."""

import shutil
from pathlib import Path

import orjson
import pytest
from click.testing import CliRunner

from scope.commands.uninstall import (
    SCOPE_COMMANDS,
    SCOPE_SKILLS,
    remove_scope_data,
    uninstall,
    uninstall_ccstatusline,
    uninstall_custom_commands,
    uninstall_skills,
)


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_claude_dir(tmp_path, monkeypatch):
    """Mock ~/.claude directory."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    def mock_settings_path():
        return claude_dir / "settings.json"

    def mock_skills_dir():
        return claude_dir / "skills"

    def mock_commands_dir():
        return claude_dir / "commands"

    monkeypatch.setattr(
        "scope.commands.uninstall.get_claude_settings_path", mock_settings_path
    )
    monkeypatch.setattr(
        "scope.commands.uninstall.get_claude_skills_dir", mock_skills_dir
    )
    monkeypatch.setattr(
        "scope.commands.uninstall.get_claude_commands_dir", mock_commands_dir
    )

    return claude_dir


@pytest.fixture
def mock_scope_dir(tmp_path, monkeypatch):
    """Mock ~/.scope directory."""
    scope_dir = tmp_path / ".scope"

    def mock_scope_data_dir():
        return scope_dir

    monkeypatch.setattr(
        "scope.commands.uninstall.get_scope_data_dir", mock_scope_data_dir
    )

    return scope_dir


# --- uninstall_skills tests ---


def test_uninstall_skills_removes_only_scope_skills(mock_claude_dir):
    """Test uninstall_skills removes only scope-installed skills."""
    skills_dir = mock_claude_dir / "skills"
    skills_dir.mkdir()

    # Create scope skills
    for skill_name in SCOPE_SKILLS:
        skill_dir = skills_dir / skill_name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"# {skill_name}")

    # Create a user skill that should NOT be removed
    user_skill_dir = skills_dir / "my-custom-skill"
    user_skill_dir.mkdir()
    (user_skill_dir / "SKILL.md").write_text("# Custom skill")

    removed = uninstall_skills()

    # All scope skills should be removed
    assert removed == len(SCOPE_SKILLS)
    for skill_name in SCOPE_SKILLS:
        assert not (skills_dir / skill_name).exists()

    # User skill should remain
    assert user_skill_dir.exists()
    assert (user_skill_dir / "SKILL.md").read_text() == "# Custom skill"


def test_uninstall_skills_handles_missing_skills(mock_claude_dir):
    """Test uninstall_skills handles missing skills gracefully."""
    skills_dir = mock_claude_dir / "skills"
    skills_dir.mkdir()

    # Create only some scope skills
    (skills_dir / "ralph").mkdir()
    (skills_dir / "ralph" / "SKILL.md").write_text("# ralph")

    removed = uninstall_skills()

    assert removed == 1
    assert not (skills_dir / "ralph").exists()


def test_uninstall_skills_handles_empty_skills_dir(mock_claude_dir):
    """Test uninstall_skills handles missing skills directory."""
    # Don't create skills dir - it doesn't exist

    removed = uninstall_skills()

    assert removed == 0


# --- uninstall_custom_commands tests ---


def test_uninstall_custom_commands_removes_only_scope_commands(mock_claude_dir):
    """Test uninstall_custom_commands removes only scope-installed commands."""
    commands_dir = mock_claude_dir / "commands"
    commands_dir.mkdir()

    # Create scope commands
    for command_file in SCOPE_COMMANDS:
        (commands_dir / command_file).write_text("# Scope command")

    # Create a user command that should NOT be removed
    user_command = commands_dir / "my-command.md"
    user_command.write_text("# My custom command")

    removed = uninstall_custom_commands()

    # All scope commands should be removed
    assert removed == len(SCOPE_COMMANDS)
    for command_file in SCOPE_COMMANDS:
        assert not (commands_dir / command_file).exists()

    # User command should remain
    assert user_command.exists()
    assert user_command.read_text() == "# My custom command"


def test_uninstall_custom_commands_handles_missing_commands(mock_claude_dir):
    """Test uninstall_custom_commands handles missing commands gracefully."""
    commands_dir = mock_claude_dir / "commands"
    commands_dir.mkdir()

    # Don't create any scope commands

    removed = uninstall_custom_commands()

    assert removed == 0


def test_uninstall_custom_commands_handles_empty_dir(mock_claude_dir):
    """Test uninstall_custom_commands handles missing commands directory."""
    # Don't create commands dir - it doesn't exist

    removed = uninstall_custom_commands()

    assert removed == 0


# --- uninstall_ccstatusline tests ---


def test_uninstall_ccstatusline_removes_when_ccstatusline(mock_claude_dir):
    """Test uninstall_ccstatusline removes statusLine if it references ccstatusline."""
    settings_path = mock_claude_dir / "settings.json"
    settings = {
        "theme": "dark",
        "statusLine": {
            "type": "command",
            "command": "npx ccstatusline@latest",
        },
    }
    settings_path.write_bytes(orjson.dumps(settings))

    result = uninstall_ccstatusline()

    assert result is True
    updated_settings = orjson.loads(settings_path.read_bytes())
    assert "statusLine" not in updated_settings
    assert updated_settings["theme"] == "dark"


def test_uninstall_ccstatusline_preserves_non_ccstatusline(mock_claude_dir):
    """Test uninstall_ccstatusline preserves statusLine if not ccstatusline."""
    settings_path = mock_claude_dir / "settings.json"
    settings = {
        "statusLine": {
            "type": "command",
            "command": "my-custom-status-command",
        },
    }
    settings_path.write_bytes(orjson.dumps(settings))

    result = uninstall_ccstatusline()

    assert result is False
    updated_settings = orjson.loads(settings_path.read_bytes())
    assert "statusLine" in updated_settings
    assert updated_settings["statusLine"]["command"] == "my-custom-status-command"


def test_uninstall_ccstatusline_handles_missing_settings(mock_claude_dir):
    """Test uninstall_ccstatusline handles missing settings file."""
    # Don't create settings file

    result = uninstall_ccstatusline()

    assert result is False


def test_uninstall_ccstatusline_handles_empty_settings(mock_claude_dir):
    """Test uninstall_ccstatusline handles empty settings file."""
    settings_path = mock_claude_dir / "settings.json"
    settings_path.write_bytes(b"")

    result = uninstall_ccstatusline()

    assert result is False


def test_uninstall_ccstatusline_handles_no_statusline(mock_claude_dir):
    """Test uninstall_ccstatusline handles settings without statusLine."""
    settings_path = mock_claude_dir / "settings.json"
    settings = {"theme": "dark"}
    settings_path.write_bytes(orjson.dumps(settings))

    result = uninstall_ccstatusline()

    assert result is False


# --- remove_scope_data tests ---


def test_remove_scope_data_removes_directory(mock_scope_dir):
    """Test remove_scope_data removes ~/.scope directory."""
    # Create scope directory with some content
    mock_scope_dir.mkdir()
    sessions_dir = mock_scope_dir / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "0").mkdir()
    (sessions_dir / "0" / "task").write_text("Test task")

    result = remove_scope_data()

    assert result is True
    assert not mock_scope_dir.exists()


def test_remove_scope_data_handles_missing_directory(mock_scope_dir):
    """Test remove_scope_data handles missing ~/.scope directory."""
    # Don't create scope dir

    result = remove_scope_data()

    assert result is False


# --- CLI uninstall command tests ---


def test_cli_uninstall_with_yes_flag(
    runner, mock_claude_dir, mock_scope_dir, monkeypatch
):
    """Test CLI uninstall command with --yes flag skips confirmation."""
    # Setup mocks for hooks and tmux
    monkeypatch.setattr("scope.commands.uninstall.uninstall_hooks", lambda: None)
    monkeypatch.setattr("scope.commands.uninstall.uninstall_tmux_hooks", lambda: None)
    monkeypatch.setattr(
        "scope.commands.uninstall.find_scope_binaries", lambda: []
    )

    # Create some scope data
    mock_scope_dir.mkdir()
    (mock_scope_dir / "sessions").mkdir()

    # Create skills and commands
    skills_dir = mock_claude_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "ralph").mkdir()
    (skills_dir / "ralph" / "SKILL.md").write_text("# ralph")

    commands_dir = mock_claude_dir / "commands"
    commands_dir.mkdir()
    (commands_dir / "scope.md").write_text("# scope")

    result = runner.invoke(uninstall, ["--yes"])

    assert result.exit_code == 0
    assert "Scope has been uninstalled" in result.output
    assert not mock_scope_dir.exists()
    assert not (skills_dir / "ralph").exists()
    assert not (commands_dir / "scope.md").exists()


def test_cli_uninstall_with_keep_data_flag(
    runner, mock_claude_dir, mock_scope_dir, monkeypatch
):
    """Test CLI uninstall command with --keep-data preserves ~/.scope."""
    # Setup mocks
    monkeypatch.setattr("scope.commands.uninstall.uninstall_hooks", lambda: None)
    monkeypatch.setattr("scope.commands.uninstall.uninstall_tmux_hooks", lambda: None)
    monkeypatch.setattr(
        "scope.commands.uninstall.find_scope_binaries", lambda: []
    )

    # Create scope data that should be preserved
    mock_scope_dir.mkdir()
    sessions_dir = mock_scope_dir / "sessions"
    sessions_dir.mkdir()
    session_dir = sessions_dir / "0"
    session_dir.mkdir()
    (session_dir / "task").write_text("Important task")

    result = runner.invoke(uninstall, ["--yes", "--keep-data"])

    assert result.exit_code == 0
    assert "Scope has been uninstalled" in result.output
    # Scope data should be preserved
    assert mock_scope_dir.exists()
    assert (session_dir / "task").read_text() == "Important task"


def test_cli_uninstall_without_confirmation_exits(runner, monkeypatch):
    """Test CLI uninstall command exits when confirmation is declined."""
    monkeypatch.setattr(
        "scope.commands.uninstall.find_scope_binaries", lambda: []
    )

    result = runner.invoke(uninstall, input="n\n")

    assert result.exit_code == 0
    assert "Uninstall cancelled" in result.output


def test_cli_uninstall_shows_binary_note(runner, mock_claude_dir, monkeypatch, tmp_path):
    """Test CLI uninstall shows note about binaries."""
    # Setup mocks
    monkeypatch.setattr("scope.commands.uninstall.uninstall_hooks", lambda: None)
    monkeypatch.setattr("scope.commands.uninstall.uninstall_tmux_hooks", lambda: None)
    monkeypatch.setattr("scope.commands.uninstall.remove_scope_data", lambda: False)

    # Mock finding binaries
    fake_binary = tmp_path / "bin" / "scope"
    fake_binary.parent.mkdir()
    fake_binary.touch()
    monkeypatch.setattr(
        "scope.commands.uninstall.find_scope_binaries",
        lambda: [fake_binary],
    )

    result = runner.invoke(uninstall, ["--yes"])

    assert result.exit_code == 0
    assert "binaries were found" in result.output
    assert "pip uninstall scopeai" in result.output


def test_cli_uninstall_reports_removed_counts(
    runner, mock_claude_dir, mock_scope_dir, monkeypatch
):
    """Test CLI uninstall reports the number of skills and commands removed."""
    # Setup mocks
    monkeypatch.setattr("scope.commands.uninstall.uninstall_hooks", lambda: None)
    monkeypatch.setattr("scope.commands.uninstall.uninstall_tmux_hooks", lambda: None)
    monkeypatch.setattr(
        "scope.commands.uninstall.find_scope_binaries", lambda: []
    )

    # Create 3 skills
    skills_dir = mock_claude_dir / "skills"
    skills_dir.mkdir()
    for skill_name in ["ralph", "tdd", "rlm"]:
        (skills_dir / skill_name).mkdir()
        (skills_dir / skill_name / "SKILL.md").write_text(f"# {skill_name}")

    # Create 1 command
    commands_dir = mock_claude_dir / "commands"
    commands_dir.mkdir()
    (commands_dir / "scope.md").write_text("# scope")

    result = runner.invoke(uninstall, ["--yes", "--keep-data"])

    assert result.exit_code == 0
    assert "Removed 3 skills" in result.output
    assert "Removed 1 commands" in result.output
