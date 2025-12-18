"""Top command - launch the scope TUI."""

import click


@click.command()
def top() -> None:
    """Launch the scope TUI.

    Shows all sessions and auto-refreshes on changes.
    """
    from scope.tui.app import ScopeApp

    app = ScopeApp()
    app.run()
