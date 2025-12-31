"""Spawn command for scope.

Creates a new scope session with Claude Code running in a tmux window.
"""

import os
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
                f"Error: alias '{alias}' already exists (session {existing.id})",
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
                click.echo(f"Error: dependency '{dep_ref}' not found", err=True)
                raise SystemExit(1)
            depends_on.append(resolved)

    # Get parent from environment (for nested sessions)
    parent = os.environ.get("SCOPE_SESSION_ID", "")

    # Get next available ID
    session_id = next_id(parent)

    # Check for cycles before creating the session
    if depends_on and detect_cycle(session_id, depends_on):
        click.echo("Error: dependency would create a cycle", err=True)
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
        if dangerously_skip_permissions and command == "claude":
            command = "claude --dangerously-skip-permissions"

        # Build environment for spawned session
        env = {"SCOPE_SESSION_ID": session_id}
        if dangerously_skip_permissions:
            env["SCOPE_DANGEROUSLY_SKIP_PERMISSIONS"] = "1"

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

        # Wait for Claude Code to start, then send the contract
        time.sleep(1)
        # Use full session:window target when not inside tmux
        if in_tmux():
            target = f":{window_name}"
        else:
            target = f"{get_scope_session()}:{window_name}"
        send_keys(target, contract)

    except TmuxError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    # Output session ID
    click.echo(session_id)
