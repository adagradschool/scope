"""Spawn command for scope.

Creates a new scope session with Claude Code running in a tmux session.
"""

import os
import time
from datetime import datetime, timezone

import click

from scope.core.contract import generate_contract
from scope.core.session import Session
from scope.core.state import ensure_scope_dir, next_id, save_session
from scope.core.tmux import TmuxError, create_session, send_keys, tmux_session_name

# Placeholder task - will be inferred from first prompt via hooks
PENDING_TASK = "(pending...)"


@click.command()
@click.argument("prompt")
def spawn(prompt: str) -> None:
    """Spawn a new scope session.

    Creates a tmux session running Claude Code with the given prompt.
    Prints the session ID to stdout.

    PROMPT is the initial prompt/context to send to Claude Code.
    The task description will be inferred automatically from the prompt.

    Examples:

        scope spawn "Write tests for the auth module in src/auth/"

        scope spawn "Fix the bug in database.py - connection times out after 30s"
    """
    # Determine parent from environment
    parent = os.environ.get("SCOPE_SESSION_ID", "")

    # Get next available ID
    session_id = next_id(parent)

    # Create session object - task will be inferred by hooks
    tmux_name = tmux_session_name(session_id)
    session = Session(
        id=session_id,
        task=PENDING_TASK,
        parent=parent,
        state="running",
        tmux_session=tmux_name,
        created_at=datetime.now(timezone.utc),
    )

    # Save session to filesystem
    save_session(session)

    # Generate and save contract
    scope_dir = ensure_scope_dir()
    contract = generate_contract(prompt=prompt)
    session_dir = scope_dir / "sessions" / session_id
    (session_dir / "contract.md").write_text(contract)

    # Create independent tmux session with Claude Code
    try:
        create_session(
            name=tmux_name,
            command="claude",
            cwd=scope_dir.parent,  # Project root
            env={"SCOPE_SESSION_ID": session_id},
        )

        # Wait for Claude Code to start, then send the contract
        time.sleep(1)
        send_keys(tmux_name, contract)

    except TmuxError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    # Output session ID
    click.echo(session_id)
