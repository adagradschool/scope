"""Setup command for scope.

Installs hooks and configures Claude Code integration.
"""

import platform

import click

from scope.core.tmux import is_installed as tmux_is_installed
from scope.hooks.install import (
    install_ccstatusline,
    install_claude_md,
    install_custom_commands,
    install_hooks,
)


@click.command()
def setup() -> None:
    """Set up scope integration with Claude Code.

    This command:

    \b
    1. Checks that tmux is installed
    2. Installs hooks into Claude Code's settings for:
       - Activity tracking: See what Claude is doing in real-time
       - Task inference: Automatically set task from first prompt
       - Completion detection: Mark sessions done when Claude exits
    3. Creates project documentation (.claude/CLAUDE.md) to teach
       Claude how to use scope for context management
    4. Configures ccstatusline to show context usage in the status bar

    Examples:

        scope setup
    """
    # 1. Check tmux
    if not tmux_is_installed():
        click.echo("tmux is not installed.", err=True)
        system = platform.system()
        if system == "Darwin":
            click.echo("Install with: brew install tmux", err=True)
        elif system == "Linux":
            click.echo(
                "Install with: apt install tmux (or your package manager)", err=True
            )
        else:
            click.echo("Please install tmux to continue.", err=True)
        raise SystemExit(1)

    click.echo("tmux found.")

    # 2. Install hooks
    click.echo("Installing scope hooks...")
    install_hooks()
    click.echo("Hooks installed to ~/.claude/settings.json")

    # 3. Create global CLAUDE.md
    click.echo("Installing global documentation...")
    install_claude_md()
    click.echo("Documentation installed to ~/.claude/CLAUDE.md")

    # 4. Install custom Claude Code commands
    click.echo("Installing custom Claude Code commands...")
    install_custom_commands()
    click.echo("Custom commands installed to ~/.claude/commands")

    # 5. Install ccstatusline with context percentage
    click.echo("Installing ccstatusline status bar...")
    install_ccstatusline()
    click.echo("Status bar configured to show context usage")

    click.echo()
    click.echo("Scope is now integrated with Claude Code.")
    click.echo("Run 'scope' to start the TUI.")
