"""Top command - launch the scope TUI."""

import os
import sys

import click


@click.command()
def top() -> None:
    """Launch the scope TUI.

    Shows all sessions and auto-refreshes on changes.
    If not running inside tmux, automatically starts tmux first.
    """
    from scope.core.tmux import get_current_session, has_session

    # If not in tmux, exec into tmux running scope top
    if get_current_session() is None:
        if has_session("scope"):
            # Attach to existing scope session
            os.execvp("tmux", ["tmux", "attach-session", "-t", "scope"])
        else:
            # Create new scope session
            os.execvp(
                "tmux", ["tmux", "new-session", "-s", "scope", sys.argv[0], "top"]
            )

    from scope.tui.app import ScopeApp

    app = ScopeApp()
    app.run()
