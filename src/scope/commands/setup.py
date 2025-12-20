"""Setup command for scope.

Installs hooks and configures Claude Code integration.
"""

import click

from scope.hooks.install import install_hooks


@click.command()
def setup() -> None:
    """Set up scope integration with Claude Code.

    This command installs hooks into Claude Code's settings that enable:

    \b
    - Activity tracking: See what Claude is doing in real-time
    - Task inference: Automatically set task from first prompt
    - Completion detection: Mark sessions done when Claude exits

    The hooks are installed to ~/.claude/settings.json.

    Examples:

        scope setup
    """
    click.echo("Installing scope hooks...")
    install_hooks()
    click.echo("Hooks installed to ~/.claude/settings.json")
    click.echo()
    click.echo("Scope is now integrated with Claude Code.")
    click.echo("Run 'scope' to start the TUI.")
