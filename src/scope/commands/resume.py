"""Resume command for scope.

Resumes a completed session by spawning a new tmux window with `claude --resume <uuid>`.
"""

import os
import shlex
from pathlib import Path

import click

from scope.core.state import (
    load_claude_session_id,
    load_session,
    resolve_id,
)
from scope.core.tmux import (
    TmuxError,
    create_window,
    get_scope_session,
    has_window_in_session,
    pane_target_for_window,
    set_pane_option,
    tmux_window_name,
)
from scope.hooks.install import install_tmux_hooks


@click.command()
@click.argument("session_ref")
@click.option(
    "--dangerously-skip-permissions",
    is_flag=True,
    envvar="SCOPE_DANGEROUSLY_SKIP_PERMISSIONS",
    help="Pass --dangerously-skip-permissions to spawned Claude instance",
)
@click.pass_context
def resume(
    ctx: click.Context, session_ref: str, dangerously_skip_permissions: bool
) -> None:
    """Resume a completed scope session.

    Restarts a done session by spawning a new tmux window with `claude --resume <uuid>`.
    The session state remains "done".

    SESSION_REF is the session ID or alias to resume (e.g., "0" or "0.1").

    Examples:

        scope resume 0

        scope resume my-alias
    """
    # Check if flag was passed via parent context
    if ctx.obj and ctx.obj.get("dangerously_skip_permissions"):
        dangerously_skip_permissions = True

    # Resolve session reference to ID
    session_id = resolve_id(session_ref)
    if session_id is None:
        click.echo(
            f"Error: Session '{session_ref}' not found\n"
            f"  Cause: '{session_ref}' is not a valid session ID or alias.\n"
            f"  Fix: List available sessions:\n"
            f"    scope poll --all",
            err=True,
        )
        raise SystemExit(1)

    # Load the session
    session = load_session(session_id)
    if session is None:
        click.echo(f"Error: Session {session_id} not found", err=True)
        raise SystemExit(1)

    # Check if session is done (resumable)
    if session.state != "done":
        click.echo(
            f"Error: Session {session_id} is not done (state: {session.state})\n"
            f"  Fix: Only done sessions can be resumed. Use 'scope spawn' for new sessions.",
            err=True,
        )
        raise SystemExit(1)

    # Load Claude session UUID
    claude_uuid = load_claude_session_id(session_id)
    if not claude_uuid:
        click.echo(
            f"Error: No Claude session UUID found for session {session_id}\n"
            f"  Cause: The session may not have been properly saved before eviction.\n"
            f"  Fix: Start a new session instead:\n"
            f'    scope spawn "Continue work on {session.task}"',
            err=True,
        )
        raise SystemExit(1)

    # Check if tmux window already exists
    window_name = tmux_window_name(session_id)
    tmux_session = get_scope_session()
    if has_window_in_session(tmux_session, window_name):
        click.echo(f"Resumed session {session_id} (recovered existing window)")
        return

    try:
        # Build command to resume Claude session
        command = f"claude --resume {shlex.quote(claude_uuid)}"
        if dangerously_skip_permissions:
            command += " --dangerously-skip-permissions"

        # Build environment for resumed session
        env = {"SCOPE_SESSION_ID": session_id}
        if dangerously_skip_permissions:
            env["SCOPE_DANGEROUSLY_SKIP_PERMISSIONS"] = "1"
        if path := os.environ.get("PATH"):
            env["PATH"] = path
        for key, value in os.environ.items():
            if key.startswith(("CLAUDE", "ANTHROPIC")):
                env[key] = value

        # Create the tmux window
        create_window(
            name=window_name,
            command=command,
            cwd=Path.cwd(),
            env=env,
        )

        # Set pane option for session tracking
        try:
            set_pane_option(
                pane_target_for_window(window_name),
                "@scope_session_id",
                session_id,
            )
        except TmuxError:
            pass

        # Ensure tmux hooks are installed
        install_tmux_hooks()

        click.echo(f"Resumed session {session_id}")

    except TmuxError as e:
        click.echo(f"Error: tmux operation failed: {e}", err=True)
        raise SystemExit(1)
