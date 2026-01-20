"""Spawn command for scope.

Creates a new scope session with Claude Code running in a tmux window.
"""

import os
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from scope.core.contract import generate_contract
from scope.core.dag import detect_cycle
from scope.core.session import Session
from scope.core.state import (
    ensure_scope_dir,
    load_session_by_alias,
    next_id,
    resolve_id,
    save_session,
)
from scope.core.tmux import (
    TmuxError,
    create_window,
    get_scope_session,
    in_tmux,
    pane_target_for_window,
    send_keys,
    set_pane_option,
    tmux_window_name,
)
from scope.hooks.install import install_tmux_hooks

# Placeholder task - will be inferred from first prompt via hooks
PENDING_TASK = "(pending...)"
CONTRACT_CHUNK_SIZE = 2000


def _task_still_pending(task_path: Path) -> bool:
    """Return True if the task file still contains the pending placeholder."""
    try:
        return task_path.read_text().strip() == PENDING_TASK
    except FileNotFoundError:
        return False


def _wait_for_task_update(task_path: Path, timeout: float) -> bool:
    """Wait for task to move past pending; return True if updated."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _task_still_pending(task_path):
            return True
        time.sleep(0.1)
    return not _task_still_pending(task_path)


def _send_contract(target: str, contract: str) -> None:
    """Send a contract to Claude Code, chunking if it is large."""
    if len(contract) <= CONTRACT_CHUNK_SIZE:
        send_keys(target, contract)
        return

    for offset in range(0, len(contract), CONTRACT_CHUNK_SIZE):
        chunk = contract[offset : offset + CONTRACT_CHUNK_SIZE]
        send_keys(target, chunk, submit=False, verify=False)
        time.sleep(0.02)
    # Allow the client to process the paste before submitting.
    time.sleep(min(2.0, max(0.2, len(contract) / 5000)))
    send_keys(target, "", submit=True, verify=False)


@click.command()
@click.argument("prompt")
@click.option(
    "--id",
    "alias",
    default="",
    help="Human-readable alias for the session (must be unique)",
)
@click.option(
    "--after",
    "after",
    default="",
    help="Comma-separated list of session IDs or aliases this session depends on",
)
@click.option(
    "--plan",
    is_flag=True,
    help="Start Claude in plan mode",
)
@click.option(
    "--model",
    default="",
    help="Model to use (e.g., sonnet, opus, haiku)",
)
@click.option(
    "--dangerously-skip-permissions",
    is_flag=True,
    envvar="SCOPE_DANGEROUSLY_SKIP_PERMISSIONS",
    help="Pass --dangerously-skip-permissions to spawned Claude instance",
)
@click.pass_context
def spawn(
    ctx: click.Context,
    prompt: str,
    alias: str,
    after: str,
    plan: bool,
    model: str,
    dangerously_skip_permissions: bool,
) -> None:
    """Spawn a new scope session.

    Creates a tmux window running Claude Code with the given prompt.
    Prints the session ID to stdout.

    PROMPT is the initial prompt/context to send to Claude Code.
    The task description will be inferred automatically from the prompt.

    Examples:

        scope spawn "Write tests for the auth module in src/auth/"

        scope spawn "Fix the bug in database.py - connection times out after 30s"
    """
    # Check if flag was passed via parent context
    if ctx.obj and ctx.obj.get("dangerously_skip_permissions"):
        dangerously_skip_permissions = True

    # Validate alias uniqueness if provided
    if alias:
        existing = load_session_by_alias(alias)
        if existing is not None:
            click.echo(
                f"Error: alias '{alias}' is already used by session {existing.id}\n"
                f"  Cause: Session aliases must be unique across all sessions.\n"
                f"  Fix: Choose a different alias:\n"
                f'    scope spawn --id {alias}-2 "your prompt here"',
                err=True,
            )
            raise SystemExit(1)

    # Parse and resolve dependencies
    depends_on: list[str] = []
    if after:
        for dep_ref in after.split(","):
            dep_ref = dep_ref.strip()
            if not dep_ref:
                continue
            resolved = resolve_id(dep_ref)
            if resolved is None:
                click.echo(
                    f"Error: dependency '{dep_ref}' not found\n"
                    f"  Cause: '{dep_ref}' is not a valid session ID or alias.\n"
                    f"  Fix: List available sessions and use a valid ID or alias:\n"
                    f"    scope list\n"
                    f'    scope spawn --after <session-id> "your prompt here"',
                    err=True,
                )
                raise SystemExit(1)
            depends_on.append(resolved)

    # Get parent from environment (for nested sessions)
    parent = os.environ.get("SCOPE_SESSION_ID", "")

    # Get next available ID
    session_id = next_id(parent)

    # Check for cycles before creating the session
    if depends_on and detect_cycle(session_id, depends_on):
        dep_list = ", ".join(depends_on)
        click.echo(
            f"Error: adding dependencies [{dep_list}] would create a circular dependency\n"
            f"  Cause: One of these sessions (or their dependencies) already depends on\n"
            f"  work that would be produced by this new session.\n"
            f"  Fix: Remove the conflicting dependency from --after, or spawn this\n"
            f"  session without dependencies and coordinate manually:\n"
            f"    scope list                              # View the dependency graph\n"
            f'    scope spawn "your prompt here"         # Spawn without --after',
            err=True,
        )
        raise SystemExit(1)

    # Create session object - task will be inferred by hooks
    window_name = tmux_window_name(session_id)
    session = Session(
        id=session_id,
        task=PENDING_TASK,
        parent=parent,
        state="running",
        tmux_session=window_name,  # Store window name (kept as tmux_session for compat)
        created_at=datetime.now(timezone.utc),
        alias=alias,
        depends_on=depends_on,
    )

    # Create tmux window with Claude Code BEFORE saving session
    # This prevents a race where load_all() sees a "running" session
    # with a tmux_session set but the window doesn't exist yet,
    # causing it to be incorrectly marked as "aborted"
    try:
        # Allow overriding command for tests (e.g., "sleep infinity" when claude isn't installed)
        command = os.environ.get("SCOPE_SPAWN_COMMAND", "claude")
        if command == "claude":
            if plan:
                command += " --permission-mode plan"
            if model:
                command += f" --model {shlex.quote(model)}"
            if dangerously_skip_permissions:
                command += " --dangerously-skip-permissions"

        # Build environment for spawned session
        env = {"SCOPE_SESSION_ID": session_id}
        if dangerously_skip_permissions:
            env["SCOPE_DANGEROUSLY_SKIP_PERMISSIONS"] = "1"
        if path := os.environ.get("PATH"):
            env["PATH"] = path
        for key, value in os.environ.items():
            if key.startswith(("CLAUDE", "ANTHROPIC")):
                env[key] = value

        create_window(
            name=window_name,
            command=command,
            cwd=Path.cwd(),  # Project root
            env=env,
        )

        try:
            set_pane_option(
                pane_target_for_window(window_name),
                "@scope_session_id",
                session_id,
            )
        except TmuxError:
            pass

        # Ensure tmux hook is installed AFTER create_window (so server exists)
        # Idempotent - safe to call on every spawn
        install_tmux_hooks()

        # Now that window exists, save session to filesystem
        save_session(session)

        # Generate and save contract
        scope_dir = ensure_scope_dir()
        session_dir = scope_dir / "sessions" / session_id

        contract = generate_contract(
            prompt=prompt, depends_on=depends_on if depends_on else None
        )
        (session_dir / "contract.md").write_text(contract)

        # Wait for Claude Code to signal readiness via SessionStart hook
        # Skip if SCOPE_SKIP_READY_CHECK is set (used in tests)
        skip_ready_check = os.environ.get("SCOPE_SKIP_READY_CHECK", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if not skip_ready_check:
            ready_file = session_dir / "ready"
            timeout = 10  # seconds
            start_time = time.time()
            while not ready_file.exists():
                if time.time() - start_time > timeout:
                    click.echo(
                        f"Warning: Claude Code did not signal ready within {timeout}s\n"
                        f"  Sending prompt anyway, but the session may not receive it correctly.\n"
                        f"  Possible causes and fixes:\n"
                        f"    - Claude Code slow to start → Wait and retry\n"
                        f"    - SessionStart hook not installed → Run: scope setup\n"
                        f"    - Claude Code crashed → Check window: tmux select-window -t {get_scope_session()}:{window_name}",
                        err=True,
                    )
                    break
                time.sleep(0.1)
            # SessionStart fires during startup but the input prompt may not be ready yet
            time.sleep(0.3)
        else:
            # In test environment, wait a short time for process to start
            time.sleep(0.5)

        # Use full session:window target when not inside tmux
        if in_tmux():
            target = f":{window_name}"
        else:
            target = f"{get_scope_session()}:{window_name}"
        _send_contract(target, contract)

        # If the task is still pending, Enter may not have been delivered.
        # Resend Enter up to 5 times to ensure the prompt submits.
        if not skip_ready_check:
            task_path = session_dir / "task"
            if _task_still_pending(task_path):
                for _ in range(5):
                    if _wait_for_task_update(task_path, timeout=1.0):
                        break
                    try:
                        send_keys(target, "", submit=True, verify=False)
                    except TmuxError:
                        pass
                _wait_for_task_update(task_path, timeout=1.0)

    except TmuxError as e:
        error_msg = str(e)
        click.echo(f"Error: tmux operation failed: {error_msg}", err=True)

        # Provide actionable guidance based on the error
        if "Failed to create" in error_msg:
            if "session" in error_msg.lower():
                click.echo(
                    "  Cause: The tmux server is not running or is inaccessible.\n"
                    "  Fix: Start tmux and verify it works:\n"
                    "    tmux new-session -d -s test && tmux kill-session -t test",
                    err=True,
                )
            else:
                click.echo(
                    "  Cause: Could not create a tmux window for this session.\n"
                    "  Fix: Verify tmux is running:\n"
                    "    tmux list-sessions",
                    err=True,
                )
        elif "send" in error_msg.lower():
            click.echo(
                "  Cause: The tmux window may have closed unexpectedly.\n"
                "  Fix: Check if Claude Code is installed and working:\n"
                "    claude --version",
                err=True,
            )
        else:
            click.echo(
                "  Cause: tmux may not be installed or is not running.\n"
                "  Fix: Install tmux:\n"
                "    brew install tmux   # macOS\n"
                "    apt install tmux    # Linux",
                err=True,
            )
        raise SystemExit(1)

    # Output session ID
    click.echo(session_id)
