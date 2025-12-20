"""CLI entry point for scope.

Usage:
    scope                     # Launch TUI (auto-starts tmux if needed)
    scope spawn "task"        # Spawn a new session
    scope poll <id>           # Check session status
    scope abort <id>          # Abort a session
"""

import os

import click

from scope.commands.abort import abort
from scope.commands.poll import poll
from scope.commands.setup import setup
from scope.commands.spawn import spawn
from scope.commands.top import top
from scope.core.tmux import in_tmux


@click.group(invoke_without_command=True)
@click.option("--inside-tmux", is_flag=True, hidden=True, help="Internal flag")
@click.version_option()
@click.pass_context
def main(ctx: click.Context, inside_tmux: bool) -> None:
    """Scope - Subagent orchestration for Claude Code.

    Spawn bounded, purpose-specific subagents. Preserve your context.
    Maintain visibility and control.

    Running 'scope' without a subcommand launches the TUI.
    """
    # If a subcommand was invoked, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    # No subcommand - launch the TUI
    if not in_tmux():
        # Not in tmux - launch tmux with scope inside
        # Use -A to attach if session exists, or create if it doesn't
        # Enable mouse mode for pane switching
        os.execvp(
            "tmux",
            ["tmux", "new-session", "-A", "-s", "scope-main", "scope", "--inside-tmux"],
        )
    else:
        # Already in tmux - run the TUI directly
        ctx.invoke(top)


# Register commands
main.add_command(spawn)
main.add_command(poll)
main.add_command(top)
main.add_command(abort)
main.add_command(setup)
