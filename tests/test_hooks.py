"""Tests for hook handler."""

from datetime import datetime, timezone
from io import StringIO

import orjson
import pytest
from click.testing import CliRunner

from scope.core.session import Session
from scope.core.state import save_session
from scope.hooks.handler import infer_activity, main, summarize_task
from scope.hooks.install import get_claude_settings_path, install_hooks, uninstall_hooks


@pytest.fixture
def runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def setup_session(mock_scope_base, monkeypatch):
    """Set up a session directory and environment."""
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


def test_activity_hook_writes_file(runner, setup_session):
    """Test activity hook writes activity file."""
    session_dir = setup_session

    input_json = orjson.dumps({
        "tool_name": "Read",
        "tool_input": {"file_path": "/path/to/auth.ts"}
    }).decode()

    result = runner.invoke(main, ["activity"], input=input_json)

    assert result.exit_code == 0
    activity_file = session_dir / "activity"
    assert activity_file.exists()
    assert activity_file.read_text() == "reading auth.ts"


def test_activity_hook_edit_tool(runner, setup_session):
    """Test activity hook with Edit tool."""
    session_dir = setup_session

    input_json = orjson.dumps({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/path/to/main.py"}
    }).decode()

    result = runner.invoke(main, ["activity"], input=input_json)

    assert result.exit_code == 0
    assert (session_dir / "activity").read_text() == "editing main.py"


def test_activity_hook_bash_tool(runner, setup_session):
    """Test activity hook with Bash tool."""
    session_dir = setup_session

    input_json = orjson.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "npm run test"}
    }).decode()

    result = runner.invoke(main, ["activity"], input=input_json)

    assert result.exit_code == 0
    assert (session_dir / "activity").read_text() == "running: npm run test"


def test_activity_hook_bash_long_command(runner, setup_session):
    """Test activity hook truncates long bash commands."""
    session_dir = setup_session

    long_command = "npm run test -- --coverage --watchAll=false --verbose"
    input_json = orjson.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": long_command}
    }).decode()

    result = runner.invoke(main, ["activity"], input=input_json)

    assert result.exit_code == 0
    activity = (session_dir / "activity").read_text()
    assert len(activity) <= 50  # "running: " + 40 chars max
    assert activity.endswith("...")


def test_activity_hook_no_session_id(runner, mock_scope_base, monkeypatch):
    """Test activity hook exits silently without session ID."""
    monkeypatch.delenv("SCOPE_SESSION_ID", raising=False)

    input_json = orjson.dumps({
        "tool_name": "Read",
        "tool_input": {"file_path": "/path/to/file.py"}
    }).decode()

    result = runner.invoke(main, ["activity"], input=input_json)

    assert result.exit_code == 0
    # No activity file should be created
    assert not (mock_scope_base / "sessions").exists()


def test_activity_hook_session_not_found(runner, mock_scope_base, monkeypatch):
    """Test activity hook exits silently if session dir doesn't exist."""
    monkeypatch.setenv("SCOPE_SESSION_ID", "999")

    input_json = orjson.dumps({
        "tool_name": "Read",
        "tool_input": {"file_path": "/path/to/file.py"}
    }).decode()

    result = runner.invoke(main, ["activity"], input=input_json)

    # Should exit cleanly without error
    assert result.exit_code == 0


def test_task_hook_sets_task(runner, setup_session, monkeypatch):
    """Test task hook sets task from first prompt."""
    session_dir = setup_session

    # Mock summarize_task to return a short summary
    monkeypatch.setattr(
        "scope.hooks.handler.summarize_task",
        lambda p: "Refactor auth module"
    )

    # Clear existing task
    task_file = session_dir / "task"
    task_file.write_text("")

    input_json = orjson.dumps({
        "prompt": "Help me refactor the auth module"
    }).decode()

    result = runner.invoke(main, ["task"], input=input_json)

    assert result.exit_code == 0
    assert task_file.read_text() == "Refactor auth module"


def test_task_hook_sets_task_once(runner, setup_session):
    """Test task hook only sets task once (first prompt)."""
    session_dir = setup_session
    task_file = session_dir / "task"

    # Set initial task
    task_file.write_text("Original task")

    input_json = orjson.dumps({
        "prompt": "This is a follow-up question"
    }).decode()

    result = runner.invoke(main, ["task"], input=input_json)

    assert result.exit_code == 0
    # Task should remain unchanged
    assert task_file.read_text() == "Original task"


def test_task_hook_overwrites_pending(runner, setup_session, monkeypatch):
    """Test task hook overwrites '(pending...)' placeholder."""
    session_dir = setup_session
    task_file = session_dir / "task"

    monkeypatch.setattr(
        "scope.hooks.handler.summarize_task",
        lambda p: "New task"
    )

    # Set placeholder
    task_file.write_text("(pending...)")

    input_json = orjson.dumps({
        "prompt": "New task from prompt"
    }).decode()

    result = runner.invoke(main, ["task"], input=input_json)

    assert result.exit_code == 0
    assert task_file.read_text() == "New task"


def test_task_hook_uses_summarizer(runner, setup_session, monkeypatch):
    """Test task hook uses summarize_task function."""
    session_dir = setup_session
    task_file = session_dir / "task"
    task_file.write_text("")

    # Track if summarize_task was called with the right prompt
    called_with = []
    def mock_summarize(prompt):
        called_with.append(prompt)
        return "Summarized task"

    monkeypatch.setattr("scope.hooks.handler.summarize_task", mock_summarize)

    input_json = orjson.dumps({
        "prompt": "This is a long prompt that needs summarization"
    }).decode()

    result = runner.invoke(main, ["task"], input=input_json)

    assert result.exit_code == 0
    assert task_file.read_text() == "Summarized task"
    assert len(called_with) == 1
    assert "long prompt" in called_with[0]


def test_task_hook_reactivates_done_session(runner, setup_session):
    """Test task hook transitions done -> running when new prompt submitted.

    Regression test: Sessions should transition from 'done' back to 'running'
    when a new command/prompt is sent to them.
    """
    session_dir = setup_session
    state_file = session_dir / "state"
    task_file = session_dir / "task"

    # Set session to done state (simulating completed session)
    state_file.write_text("done")
    task_file.write_text("Original task")

    input_json = orjson.dumps({
        "prompt": "A follow-up request"
    }).decode()

    result = runner.invoke(main, ["task"], input=input_json)

    assert result.exit_code == 0
    # State should transition from done to running
    assert state_file.read_text() == "running"
    # Task should remain unchanged (already set)
    assert task_file.read_text() == "Original task"


def test_task_hook_does_not_change_running_state(runner, setup_session):
    """Test task hook does not modify state if already running."""
    session_dir = setup_session
    state_file = session_dir / "state"
    task_file = session_dir / "task"

    # Session is already running
    state_file.write_text("running")
    task_file.write_text("Current task")

    input_json = orjson.dumps({
        "prompt": "Another request"
    }).decode()

    result = runner.invoke(main, ["task"], input=input_json)

    assert result.exit_code == 0
    # State should remain running
    assert state_file.read_text() == "running"


def test_stop_hook_marks_done(runner, setup_session):
    """Test stop hook marks session as done."""
    session_dir = setup_session
    state_file = session_dir / "state"

    # Verify initial state is running
    assert state_file.read_text() == "running"

    result = runner.invoke(main, ["stop"])

    assert result.exit_code == 0
    assert state_file.read_text() == "done"


def test_stop_hook_preserves_activity(runner, setup_session):
    """Test stop hook preserves activity file."""
    session_dir = setup_session
    activity_file = session_dir / "activity"

    # Set some activity
    activity_file.write_text("editing file.py")

    result = runner.invoke(main, ["stop"])

    assert result.exit_code == 0
    assert activity_file.read_text() == "editing file.py"


def test_stop_hook_captures_result(runner, setup_session, tmp_path):
    """Test stop hook writes result from transcript."""
    session_dir = setup_session

    # Create a mock transcript file
    transcript_file = tmp_path / "transcript.jsonl"
    transcript_lines = [
        orjson.dumps({"type": "user", "message": {"content": "Hello"}}).decode(),
        orjson.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Here is the result."}]
            }
        }).decode(),
    ]
    transcript_file.write_text("\n".join(transcript_lines))

    input_json = orjson.dumps({
        "transcript_path": str(transcript_file)
    }).decode()

    result = runner.invoke(main, ["stop"], input=input_json)

    assert result.exit_code == 0
    result_file = session_dir / "result"
    assert result_file.exists()
    assert result_file.read_text() == "Here is the result."


def test_stop_hook_captures_last_assistant_message(runner, setup_session, tmp_path):
    """Test stop hook captures the last assistant message from transcript."""
    session_dir = setup_session

    # Create transcript with multiple assistant messages
    transcript_file = tmp_path / "transcript.jsonl"
    transcript_lines = [
        orjson.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "First response"}]}
        }).decode(),
        orjson.dumps({"type": "user", "message": {"content": "More questions"}}).decode(),
        orjson.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Final answer"}]}
        }).decode(),
    ]
    transcript_file.write_text("\n".join(transcript_lines))

    input_json = orjson.dumps({"transcript_path": str(transcript_file)}).decode()
    result = runner.invoke(main, ["stop"], input=input_json)

    assert result.exit_code == 0
    assert (session_dir / "result").read_text() == "Final answer"


def test_infer_activity_read():
    """Test infer_activity for Read tool."""
    assert infer_activity("Read", {"file_path": "/path/to/file.py"}) == "reading file.py"
    assert infer_activity("Read", {}) == "reading file"


def test_infer_activity_edit():
    """Test infer_activity for Edit tool."""
    assert infer_activity("Edit", {"file_path": "/path/to/main.ts"}) == "editing main.ts"
    assert infer_activity("Write", {"file_path": "/path/to/new.js"}) == "editing new.js"


def test_infer_activity_bash():
    """Test infer_activity for Bash tool."""
    assert infer_activity("Bash", {"command": "ls -la"}) == "running: ls -la"
    long_cmd = "a" * 50
    result = infer_activity("Bash", {"command": long_cmd})
    assert result == "running: " + "a" * 37 + "..."


def test_infer_activity_grep():
    """Test infer_activity for Grep tool."""
    assert infer_activity("Grep", {"pattern": "TODO"}) == "searching: TODO"


def test_infer_activity_task():
    """Test infer_activity for Task tool."""
    assert infer_activity("Task", {}) == "spawning subtask"


def test_infer_activity_glob():
    """Test infer_activity for Glob tool."""
    assert infer_activity("Glob", {"pattern": "**/*.py"}) == "finding: **/*.py"


def test_infer_activity_unknown():
    """Test infer_activity for unknown tools."""
    assert infer_activity("WebSearch", {}) == "websearch"
    assert infer_activity("AskUser", {}) == "askuser"


# --- Install tests ---


@pytest.fixture
def mock_claude_dir(tmp_path, monkeypatch):
    """Mock ~/.claude directory."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    def mock_path():
        return claude_dir / "settings.json"

    monkeypatch.setattr(
        "scope.hooks.install.get_claude_settings_path", mock_path
    )
    return claude_dir


def test_install_hooks_creates_config(mock_claude_dir):
    """Test install_hooks creates settings.json if missing."""
    settings_path = mock_claude_dir / "settings.json"
    assert not settings_path.exists()

    install_hooks()

    assert settings_path.exists()
    settings = orjson.loads(settings_path.read_bytes())
    assert "hooks" in settings
    assert "PostToolUse" in settings["hooks"]
    assert "UserPromptSubmit" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_install_hooks_preserves_existing(mock_claude_dir):
    """Test install_hooks preserves existing settings."""
    settings_path = mock_claude_dir / "settings.json"
    existing = {
        "theme": "dark",
        "permissions": {"allow_read": True},
    }
    settings_path.write_bytes(orjson.dumps(existing))

    install_hooks()

    settings = orjson.loads(settings_path.read_bytes())
    assert settings["theme"] == "dark"
    assert settings["permissions"]["allow_read"] is True
    assert "hooks" in settings


def test_install_hooks_preserves_existing_hooks(mock_claude_dir):
    """Test install_hooks preserves existing hooks."""
    settings_path = mock_claude_dir / "settings.json"
    existing = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "my-custom-hook"}],
                }
            ]
        }
    }
    settings_path.write_bytes(orjson.dumps(existing))

    install_hooks()

    settings = orjson.loads(settings_path.read_bytes())
    post_tool_hooks = settings["hooks"]["PostToolUse"]

    # Should have both custom and scope hooks
    commands = [
        h["hooks"][0]["command"]
        for h in post_tool_hooks
    ]
    assert "my-custom-hook" in commands
    assert "scope-hook activity" in commands


def test_install_hooks_idempotent(mock_claude_dir):
    """Test install_hooks is idempotent (no duplicate hooks)."""
    settings_path = mock_claude_dir / "settings.json"

    # Install twice
    install_hooks()
    install_hooks()

    settings = orjson.loads(settings_path.read_bytes())
    post_tool_hooks = settings["hooks"]["PostToolUse"]

    # Should only have one scope-hook activity entry
    scope_hooks = [
        h for h in post_tool_hooks
        if h["hooks"][0]["command"] == "scope-hook activity"
    ]
    assert len(scope_hooks) == 1


def test_uninstall_hooks_removes_scope_hooks(mock_claude_dir):
    """Test uninstall_hooks removes only scope hooks."""
    settings_path = mock_claude_dir / "settings.json"
    existing = {
        "hooks": {
            "PostToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "my-hook"}]},
                {"matcher": "*", "hooks": [{"type": "command", "command": "scope-hook activity"}]},
            ]
        }
    }
    settings_path.write_bytes(orjson.dumps(existing))

    uninstall_hooks()

    settings = orjson.loads(settings_path.read_bytes())
    commands = [
        h["hooks"][0]["command"]
        for h in settings["hooks"]["PostToolUse"]
    ]
    assert "my-hook" in commands
    assert "scope-hook activity" not in commands


def test_uninstall_hooks_no_file(mock_claude_dir):
    """Test uninstall_hooks handles missing settings file."""
    # Should not raise
    uninstall_hooks()


# --- Summarize task tests ---


def test_summarize_task_fallback_short(monkeypatch):
    """Test summarize_task returns short prompt as-is when Claude fails."""
    # Mock subprocess to fail
    import subprocess
    def mock_run(*args, **kwargs):
        raise FileNotFoundError("claude not found")

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = summarize_task("Fix the bug")
    assert result == "Fix the bug"


def test_summarize_task_fallback_truncates(monkeypatch):
    """Test summarize_task truncates long prompt when Claude fails."""
    import subprocess
    def mock_run(*args, **kwargs):
        raise FileNotFoundError("claude not found")

    monkeypatch.setattr(subprocess, "run", mock_run)

    long_prompt = "This is a very long prompt that exceeds the maximum length limit"
    result = summarize_task(long_prompt)
    assert len(result) <= 50
    assert result.endswith("...")


def test_summarize_task_uses_claude(monkeypatch):
    """Test summarize_task calls Claude CLI and returns summary."""
    import subprocess

    class MockResult:
        returncode = 0
        stdout = "Fix auth bug"

    def mock_run(cmd, **kwargs):
        assert cmd[0] == "claude"
        assert cmd[1] == "-p"
        assert "task title generator" in cmd[2]
        assert "3-5 word" in cmd[2]
        return MockResult()

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = summarize_task("Help me fix the authentication bug in the login module")
    assert result == "Fix auth bug"


def test_summarize_task_rejects_long_summary(monkeypatch):
    """Test summarize_task falls back if Claude returns too long response."""
    import subprocess

    class MockResult:
        returncode = 0
        stdout = "This is a very long summary that exceeds sixty characters and should be rejected"

    def mock_run(cmd, **kwargs):
        return MockResult()

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = summarize_task("Short prompt")
    assert result == "Short prompt"  # Falls back to original


# --- Block background scope tests ---


def test_block_background_scope_allows_normal_scope(runner):
    """Test block-background-scope allows scope commands without run_in_background."""
    input_json = orjson.dumps({
        "tool_input": {
            "command": "scope spawn 'do something'",
            "run_in_background": False,
        }
    }).decode()

    result = runner.invoke(main, ["block-background-scope"], input=input_json)
    assert result.exit_code == 0


def test_block_background_scope_blocks_background_scope(runner):
    """Test block-background-scope blocks scope commands with run_in_background=true."""
    input_json = orjson.dumps({
        "tool_input": {
            "command": "scope spawn 'do something'",
            "run_in_background": True,
        }
    }).decode()

    result = runner.invoke(main, ["block-background-scope"], input=input_json)
    assert result.exit_code == 1
    assert "BLOCKED" in result.output


def test_block_background_scope_allows_background_non_scope(runner):
    """Test block-background-scope allows non-scope commands with run_in_background."""
    input_json = orjson.dumps({
        "tool_input": {
            "command": "npm run build",
            "run_in_background": True,
        }
    }).decode()

    result = runner.invoke(main, ["block-background-scope"], input=input_json)
    assert result.exit_code == 0


def test_block_background_scope_allows_normal_non_scope(runner):
    """Test block-background-scope allows non-scope commands without run_in_background."""
    input_json = orjson.dumps({
        "tool_input": {
            "command": "git status",
        }
    }).decode()

    result = runner.invoke(main, ["block-background-scope"], input=input_json)
    assert result.exit_code == 0


def test_block_background_scope_handles_whitespace(runner):
    """Test block-background-scope handles commands with leading whitespace."""
    input_json = orjson.dumps({
        "tool_input": {
            "command": "  scope wait abc123",
            "run_in_background": True,
        }
    }).decode()

    result = runner.invoke(main, ["block-background-scope"], input=input_json)
    assert result.exit_code == 1
    assert "BLOCKED" in result.output
