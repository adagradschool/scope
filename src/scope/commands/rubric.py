"""Rubric command for scope.

Opens the rubric file for a session in $EDITOR for mid-loop editing.
"""

import os
import subprocess
from pathlib import Path

import click

from scope.core.state import load_loop_state, resolve_id


@click.command()
@click.argument("session_id")
def rubric(session_id: str) -> None:
    """Open the rubric for a session in $EDITOR.

    SESSION_ID is the session ID or alias. The rubric file is read fresh
    each iteration, so edits take effect on the next checker run.

    Examples:

        scope rubric 0

        scope rubric my-search-task
    """
    resolved = resolve_id(session_id)
    if resolved is None:
        click.echo(f"Error: session not found: {session_id}", err=True)
        raise SystemExit(1)

    loop_state = load_loop_state(resolved)
    if loop_state is None:
        click.echo(f"Error: no loop state for session {resolved}", err=True)
        raise SystemExit(1)

    rubric_path = loop_state.get("rubric_path", "")
    if not rubric_path:
        click.echo(f"Error: no rubric file for session {resolved}", err=True)
        raise SystemExit(1)

    if not Path(rubric_path).exists():
        click.echo(f"Error: rubric file not found: {rubric_path}", err=True)
        raise SystemExit(1)

    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, rubric_path])
