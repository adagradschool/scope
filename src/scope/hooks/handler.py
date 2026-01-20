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

from scope.core.project import get_global_scope_base_for
from scope.core.state import get_global_scope_base


def get_session_dir() -> Path | None:
    """Get the session directory from SCOPE_SESSION_ID env var.

    Returns None if not in a scope session or session dir doesn't exist.
    """
    session_id = os.environ.get("SCOPE_SESSION_ID", "")
    if not session_id:
        return None

    session_dir = get_global_scope_base() / "sessions" / session_id

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


@main.command("block-background-scope")
def block_background_scope() -> None:
    """Block Bash commands that run scope CLI in background.

    Used as a PreToolUse hook to prevent `scope spawn/wait/poll` from
    being run with run_in_background=true, which would make them opaque.
    """
    data = read_stdin_json()
    tool_input = data.get("tool_input", {})

    run_in_background = tool_input.get("run_in_background", False)
    command = tool_input.get("command", "")

    # Only block if both conditions are true
    if run_in_background and command.strip().startswith("scope"):
        click.echo(
            "BLOCKED: scope commands must not run in background. "
            "Remove run_in_background=true from the Bash call.",
            err=True,
        )
        sys.exit(1)


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
    if activity_file.exists():
        existing = activity_file.read_text()
        prefix = "" if existing.endswith("\n") or not existing else "\n"
        activity_file.write_text(f"{existing}{prefix}{activity_str}")
    else:
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
    """Handle UserPromptSubmit hook - set task from first prompt and reactivate done sessions."""
    session_dir = get_session_dir()
    if session_dir is None:
        return

    data = read_stdin_json()
    prompt = data.get("prompt", "")

    if not prompt:
        return

    # Transition done -> running when new prompt is submitted
    state_file = session_dir / "state"
    if state_file.exists():
        current_state = state_file.read_text().strip()
        if current_state == "done":
            state_file.write_text("running")

    # Only set task if it's empty or contains placeholder
    task_file = session_dir / "task"
    if task_file.exists():
        current_task = task_file.read_text().strip()
        if current_task and current_task != "(pending...)":
            # Task already set, don't overwrite
            return

    summary = summarize_task(prompt)
    task_file.write_text(summary)


def extract_final_response(transcript_path: str) -> str | None:
    """Extract the final assistant response from a transcript JSONL file.

    Args:
        transcript_path: Path to the conversation transcript (.jsonl)

    Returns:
        The text content of the last assistant message, or None if not found.
    """
    path = Path(transcript_path).expanduser()
    if not path.exists():
        return None

    last_assistant_message = None

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = orjson.loads(line)
                # Look for assistant messages
                if entry.get("type") == "assistant":
                    message = entry.get("message", {})
                    content = message.get("content", [])
                    # Extract text blocks from content
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    if text_parts:
                        last_assistant_message = "\n".join(text_parts)
            except (orjson.JSONDecodeError, KeyError, TypeError):
                continue

    return last_assistant_message


def build_trajectory_index(transcript_path: str) -> dict | None:
    """Build an index summarizing the trajectory from a transcript.

    Args:
        transcript_path: Path to the conversation transcript (.jsonl)

    Returns:
        Dictionary with trajectory statistics, or None if transcript not found.
    """
    path = Path(transcript_path).expanduser()
    if not path.exists():
        return None

    tool_calls: list[str] = []
    turn_count = 0
    model = None
    first_timestamp = None
    last_timestamp = None

    # Token usage tracking
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_creation_tokens = 0
    total_cache_read_tokens = 0
    final_context_tokens = 0  # Context window size at end of session

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = orjson.loads(line)
                entry_type = entry.get("type", "")

                # Track timestamps
                timestamp = entry.get("timestamp")
                if timestamp:
                    if first_timestamp is None:
                        first_timestamp = timestamp
                    last_timestamp = timestamp

                # Count turns (user + assistant messages)
                if entry_type in ("user", "assistant"):
                    turn_count += 1

                # Extract model from assistant messages
                if entry_type == "assistant" and model is None:
                    message = entry.get("message", {})
                    model = message.get("model")

                # Track tool calls and token usage from assistant messages
                if entry_type == "assistant":
                    message = entry.get("message", {})
                    content = message.get("content", [])
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_name = block.get("name", "unknown")
                            tool_calls.append(tool_name)

                    # Track token usage
                    usage = message.get("usage", {})
                    if usage:
                        total_input_tokens += usage.get("input_tokens", 0)
                        total_output_tokens += usage.get("output_tokens", 0)
                        total_cache_creation_tokens += usage.get(
                            "cache_creation_input_tokens", 0
                        )
                        total_cache_read_tokens += usage.get(
                            "cache_read_input_tokens", 0
                        )
                        # Track final context size (input + cache read = full context)
                        final_context_tokens = usage.get("input_tokens", 0) + usage.get(
                            "cache_read_input_tokens", 0
                        )

            except (orjson.JSONDecodeError, KeyError, TypeError):
                continue

    # Calculate duration
    duration_seconds = None
    if first_timestamp and last_timestamp:
        try:
            from datetime import datetime

            # Parse ISO timestamps
            first_dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
            last_dt = datetime.fromisoformat(last_timestamp.replace("Z", "+00:00"))
            duration_seconds = int((last_dt - first_dt).total_seconds())
        except (ValueError, TypeError):
            pass

    # Build tool summary
    tool_summary: dict[str, int] = {}
    for tool in tool_calls:
        tool_summary[tool] = tool_summary.get(tool, 0) + 1

    # Build usage summary
    usage = {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "cache_creation_tokens": total_cache_creation_tokens,
        "cache_read_tokens": total_cache_read_tokens,
    }

    return {
        "turn_count": turn_count,
        "tool_calls": tool_calls,
        "tool_summary": tool_summary,
        "duration_seconds": duration_seconds,
        "model": model,
        "usage": usage,
        "context_used": final_context_tokens,
    }


def copy_trajectory(transcript_path: str, session_dir: Path) -> bool:
    """Copy transcript to session directory and build index.

    Args:
        transcript_path: Path to the source transcript (.jsonl)
        session_dir: Path to the session directory

    Returns:
        True if successful, False otherwise.
    """
    import shutil

    path = Path(transcript_path).expanduser()
    if not path.exists():
        return False

    # Copy full transcript
    trajectory_file = session_dir / "trajectory.jsonl"
    shutil.copy2(path, trajectory_file)

    # Build and save index
    index = build_trajectory_index(transcript_path)
    if index:
        index_file = session_dir / "trajectory_index.json"
        index_file.write_bytes(orjson.dumps(index, option=orjson.OPT_INDENT_2))

    return True


@main.command()
def ready() -> None:
    """Handle SessionStart hook - signal that Claude Code is ready to receive input."""
    session_dir = get_session_dir()
    if session_dir is None:
        return

    # Create ready signal file
    ready_file = session_dir / "ready"
    ready_file.touch()


def get_latest_context_usage(transcript_path: str) -> dict | None:
    """Extract the latest context usage from the last assistant message.

    Args:
        transcript_path: Path to the conversation transcript (.jsonl)

    Returns:
        Dictionary with context usage info, or None if not found.
    """
    path = Path(transcript_path).expanduser()
    if not path.exists():
        return None

    last_usage = None

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = orjson.loads(line)
                if entry.get("type") == "assistant":
                    message = entry.get("message", {})
                    usage = message.get("usage", {})
                    if usage:
                        last_usage = usage
            except (orjson.JSONDecodeError, KeyError, TypeError):
                continue

    if not last_usage:
        return None

    # Calculate total context (input + cache read)
    input_tokens = last_usage.get("input_tokens", 0)
    cache_read = last_usage.get("cache_read_input_tokens", 0)
    cache_creation = last_usage.get("cache_creation_input_tokens", 0)
    output_tokens = last_usage.get("output_tokens", 0)
    total_context = input_tokens + cache_read + cache_creation

    return {
        "context_tokens": total_context,
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "output_tokens": output_tokens,
    }


def find_current_transcript() -> Path | None:
    """Find the most recently modified transcript for the current project.

    Returns the path to the most recent .jsonl file in the project's Claude logs.
    """
    cwd = Path.cwd()

    # Build the project key path (Claude uses path with - replacing /)
    project_key = str(cwd).replace("/", "-")
    if project_key.startswith("-"):
        project_key = project_key[1:]

    projects_dir = Path.home() / ".claude" / "projects" / f"-{project_key}"

    if not projects_dir.exists():
        return None

    # Find the most recently modified .jsonl file (excluding agent-* files)
    jsonl_files = [
        f for f in projects_dir.glob("*.jsonl") if not f.name.startswith("agent-")
    ]

    if not jsonl_files:
        return None

    # Sort by modification time, newest first
    jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return jsonl_files[0]


@main.command()
def context() -> None:
    """Report current context usage to stderr (visible to Claude).

    This hook reads the transcript and outputs context usage info to stderr,
    which Claude Code surfaces back to the assistant.
    """
    data = read_stdin_json()
    transcript_path = data.get("transcript_path", "")

    if not transcript_path:
        return

    usage = get_latest_context_usage(transcript_path)
    if not usage:
        return

    # Format context as percentage of 200k limit
    context_tokens = usage["context_tokens"]
    context_pct = (context_tokens / 200_000) * 100

    # Output to stderr - this is surfaced to Claude
    click.echo(
        f"[context: {context_tokens:,} tokens ({context_pct:.1f}% of 200k)]",
        err=True,
    )


# Context threshold for forcing spawn (100k tokens)
CONTEXT_SPAWN_THRESHOLD = 100_000


@main.command("context-gate")
def context_gate() -> None:
    """PreToolUse hook to force spawning when context exceeds threshold.

    Blocks most tools when context > 100k tokens, forcing the agent to
    spawn subtasks instead. Only allows Bash for `scope` commands.
    """
    data = read_stdin_json()
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    # Always allow scope commands (spawn, wait, poll)
    if tool_name == "Bash":
        command = tool_input.get("command", "").strip()
        if command.startswith("scope "):
            return

    # Block these tools when over threshold
    gated_tools = {"Edit", "Write", "Bash", "NotebookEdit", "Read", "Grep", "Glob"}
    if tool_name not in gated_tools:
        return

    # Find current transcript
    transcript = find_current_transcript()
    if not transcript:
        return  # Can't determine context, allow action

    usage = get_latest_context_usage(str(transcript))
    if not usage:
        return  # No usage data yet, allow action

    context_tokens = usage["context_tokens"]
    if context_tokens <= CONTEXT_SPAWN_THRESHOLD:
        return  # Under threshold, allow action

    # Over threshold - block action tools
    context_pct = (context_tokens / 200_000) * 100
    click.echo(
        f"BLOCKED: Context ({context_tokens:,} tokens, {context_pct:.1f}%) exceeds 100k threshold.\n"
        f"You must spawn subagents to continue. Choose one:\n"
        f'  1. HANDOFF: scope spawn "Continue: [current status + what remains]"\n'
        f"  2. SPLIT: spawn multiple focused subtasks for remaining work",
        err=True,
    )
    sys.exit(2)  # Exit code 2 = blocking error in Claude Code


@main.command()
def stop() -> None:
    """Handle Stop hook - mark session as done, capture result, and store trajectory."""
    session_dir = get_session_dir()
    if session_dir is None:
        return

    # Extract final response from transcript and copy full trajectory
    data = read_stdin_json()
    transcript_path = data.get("transcript_path", "")
    if transcript_path:
        final_response = extract_final_response(transcript_path)
        if final_response:
            result_file = session_dir / "result"
            result_file.write_text(final_response)

        # Copy full trajectory and build index
        copy_trajectory(transcript_path, session_dir)

    # Update state to done
    state_file = session_dir / "state"
    state_file.write_text("done")


@main.command("pane-died")
@click.argument("window_name")
@click.argument("pane_id")
@click.argument("scope_session_id", required=False)
@click.argument("pane_path", required=False)
def pane_died(
    window_name: str,
    pane_id: str,
    scope_session_id: str | None = None,
    pane_path: str | None = None,
) -> None:
    """Handle tmux pane-died hook - mark session as exited if it was running.

    Called by tmux when a pane's program dies (with remain-on-exit=on).
    Converts window name to session ID and updates state to 'exited'.

    Args:
        window_name: The tmux window name (e.g., "w0-2" for session "0.2")
        pane_id: The tmux pane ID (e.g., "%5") to kill after processing
        scope_session_id: Explicit scope session ID set on the pane (optional)
        pane_path: The pane's working directory (for project resolution)
    """
    import subprocess

    # Backward-compat: old hook passes pane_path as third arg
    if scope_session_id and pane_path is None and Path(scope_session_id).is_absolute():
        pane_path = scope_session_id
        scope_session_id = None

    # Determine session id from pane option or window name
    session_id = scope_session_id or ""
    if not session_id:
        if not window_name.startswith("w"):
            return
        session_id = window_name[1:].replace("-", ".")

    # Resolve scope base from pane path when provided (tmux hooks run out-of-tree)
    scope_base = get_global_scope_base()
    if pane_path:
        scope_base = get_global_scope_base_for(Path(pane_path))

    # Get session directory
    session_dir = scope_base / "sessions" / session_id
    if not session_dir.exists():
        return

    state_file = session_dir / "state"
    if not state_file.exists():
        return

    # Mark as exited if running or done (pane exit is authoritative)
    current_state = state_file.read_text().strip()
    if current_state in ("running", "done"):
        state_file.write_text("exited")

    # Touch trigger file to notify TUI
    trigger_file = scope_base / "pane-exited"
    trigger_file.touch()

    # Kill the pane (it's kept alive by remain-on-exit so we can read window_name)
    if pane_id:
        try:
            subprocess.run(["tmux", "kill-pane", "-t", pane_id], capture_output=True)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
