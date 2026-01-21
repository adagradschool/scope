"""Proxy tk (ticket) commands through scope."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click

from scope.core.state import ensure_scope_dir, resolve_id


def _resolve_session_id(session_ref: str) -> str:
    """Resolve a session ID or alias to a concrete session ID."""
    resolved = resolve_id(session_ref)
    if resolved is None:
        raise click.ClickException(f"Session '{session_ref}' not found")
    return resolved


def _tickets_dir_for(session_id: str) -> Path:
    scope_dir = ensure_scope_dir()
    session_dir = scope_dir / "sessions" / session_id
    if not session_dir.exists():
        raise click.ClickException(f"Session '{session_id}' not found")
    tickets_dir = session_dir / ".tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    return tickets_dir


@click.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.option(
    "--session",
    "session_ref",
    default="",
    help="Scope session ID or alias (defaults to $SCOPE_SESSION_ID)",
)
@click.pass_context
def tk(ctx: click.Context, session_ref: str) -> None:
    """Run tk with a per-session ticket store."""
    session_ref = session_ref or os.environ.get("SCOPE_SESSION_ID", "")
    if not session_ref:
        raise click.ClickException(
            "No session specified. Use --session or set $SCOPE_SESSION_ID."
        )

    session_id = _resolve_session_id(session_ref)
    tickets_dir = _tickets_dir_for(session_id)

    env = os.environ.copy()
    env["TICKETS_DIR"] = str(tickets_dir)

    result = subprocess.run(["tk", *ctx.args], env=env)
    raise SystemExit(result.returncode)
