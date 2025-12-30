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
from scope.commands.wait import wait
from scope.core.tmux import in_tmux


@click.group(invoke_without_command=True)
@click.option("--inside-tmux", is_flag=True, hidden=True, help="Internal flag")
@click.option(
    "--dangerously-skip-permissions",
    is_flag=True,
    envvar="SCOPE_DANGEROUSLY_SKIP_PERMISSIONS",
    help="Pass --dangerously-skip-permissions to spawned Claude instances",
)
@click.version_option(package_name="scopeai")
@click.pass_context
def main(
    ctx: click.Context, inside_tmux: bool, dangerously_skip_permissions: bool
) -> None:
    """Scope - Subagent orchestration for Claude Code.

    Spawn bounded, purpose-specific subagents. Preserve your context.
    Maintain visibility and control.

    Running 'scope' without a subcommand launches the TUI.
    """
    # Store in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["dangerously_skip_permissions"] = dangerously_skip_permissions

    # If a subcommand was invoked, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    # No subcommand - launch the TUI
    if not in_tmux():
        # Not in tmux - launch tmux with scope inside
        # Use -A to attach if session exists, or create if it doesn't
        # Build command with env vars prefixed (tmux doesn't inherit parent env reliably)
        scope_cmd = ""
        if dangerously_skip_permissions:
            scope_cmd = "SCOPE_DANGEROUSLY_SKIP_PERMISSIONS=1 "
        scope_cmd += "scope --inside-tmux"
        if dangerously_skip_permissions:
            scope_cmd += " --dangerously-skip-permissions"

        os.execvp("tmux", ["tmux", "new-session", "-A", "-s", "scope-main", scope_cmd])
    else:
        # Already in tmux - run the TUI directly
        ctx.invoke(top, dangerously_skip_permissions=dangerously_skip_permissions)


# Register commands
main.add_command(spawn)
main.add_command(poll)
main.add_command(top)
main.add_command(abort)
main.add_command(setup)
main.add_command(wait)
