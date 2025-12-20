"""Hook handler for Claude Code integration.

This module provides the `scope-hook` CLI command that is called by Claude Code
hooks to update session activity and state.

Entry point defined in pyproject.toml:
    scope-hook = "scope.hooks.handler:main"
"""

import os
import sys
from pathlib import Path

import click
import orjson


def get_session_dir() -> Path | None:
    """Get the session directory from SCOPE_SESSION_ID env var.

    Returns None if not in a scope session or session dir doesn't exist.
    """
    session_id = os.environ.get("SCOPE_SESSION_ID", "")
    if not session_id:
        return None

    session_dir = Path.cwd() / ".scope" / "sessions" / session_id
    if not session_dir.exists():
        return None

    return session_dir


def read_stdin_json() -> dict:
    """Read and parse JSON from stdin."""
    try:
        data = sys.stdin.read()
        if not data:
            return {}
        return orjson.loads(data)
    except (orjson.JSONDecodeError, ValueError):
        return {}


def infer_activity(tool_name: str, tool_input: dict) -> str:
    """Infer activity string from tool name and input.

    Args:
        tool_name: Name of the tool being used
        tool_input: Tool input parameters

    Returns:
        Human-readable activity string
    """
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path:
            # Show just filename or last part of path
            name = Path(file_path).name
            return f"reading {name}"
        return "reading file"

    if tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            name = Path(file_path).name
            return f"editing {name}"
        return "editing file"

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if command:
            # Truncate long commands
            if len(command) > 40:
                command = command[:37] + "..."
            return f"running: {command}"
        return "running command"

    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        if pattern:
            if len(pattern) > 30:
                pattern = pattern[:27] + "..."
            return f"searching: {pattern}"
        return "searching"

    if tool_name == "Task":
        return "spawning subtask"

    if tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        if pattern:
            return f"finding: {pattern}"
        return "finding files"

    # Default: just show tool name
    return tool_name.lower()


@click.group()
def main() -> None:
    """Hook handler for Claude Code integration."""
    pass


@main.command()
def activity() -> None:
    """Handle PostToolUse hook - update activity file."""
    session_dir = get_session_dir()
    if session_dir is None:
        return

    data = read_stdin_json()
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if not tool_name:
        return

    activity_str = infer_activity(tool_name, tool_input)
    activity_file = session_dir / "activity"
    activity_file.write_text(activity_str)


def summarize_task(prompt: str) -> str:
    """Summarize a prompt into a short task description using Claude CLI.

    Args:
        prompt: The full user prompt

    Returns:
        A 3-5 word summary, or truncated first line as fallback
    """
    import subprocess

    # Fallback: truncated first line
    first_line = prompt.split("\n")[0].strip()
    if len(first_line) > 50:
        fallback = first_line[:47] + "..."
    else:
        fallback = first_line

    try:
        # Use env to prevent hook recursion - unset SCOPE_SESSION_ID
        # so the claude call doesn't trigger our hooks
        env = os.environ.copy()
        env.pop("SCOPE_SESSION_ID", None)

        result = subprocess.run(
            [
                "claude",
                "-p",
                "You are a task title generator. Given a user request, output ONLY a 3-5 word title. "
                "No explanation, no execution, no quotes, no punctuation. Just the title.\n\n"
                f"User request: {prompt[:500]}\n\nTitle:",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode == 0 and result.stdout.strip():
            summary = result.stdout.strip()
            # Sanity check: should be short
            if len(summary) <= 60:
                return summary

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return fallback


@main.command()
def task() -> None:
    """Handle UserPromptSubmit hook - set task from first prompt."""
    session_dir = get_session_dir()
    if session_dir is None:
        return

    # Only set task if it's empty or contains placeholder
    task_file = session_dir / "task"
    if task_file.exists():
        current_task = task_file.read_text().strip()
        if current_task and current_task != "(pending...)":
            # Task already set, don't overwrite
            return

    data = read_stdin_json()
    prompt = data.get("prompt", "")

    if not prompt:
        return

    summary = summarize_task(prompt)
    task_file.write_text(summary)


@main.command()
def stop() -> None:
    """Handle Stop hook - mark session as done."""
    session_dir = get_session_dir()
    if session_dir is None:
        return

    # Update state to done
    state_file = session_dir / "state"
    state_file.write_text("done")

    # Clear activity
    activity_file = session_dir / "activity"
    if activity_file.exists():
        activity_file.write_text("")


if __name__ == "__main__":
    main()
