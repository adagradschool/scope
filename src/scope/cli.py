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
from scope.commands.estimate import estimate
from scope.commands.poll import poll
from scope.commands.setup import setup
from scope.commands.spawn import spawn
from scope.commands.trajectory import trajectory
from scope.commands.update import update
from scope.commands.wait import wait
from scope.core.tmux import (
    TmuxError,
    create_window,
    get_scope_session,
    has_session,
    has_window_in_session,
    in_tmux,
    is_window_dead,
    kill_window_in_session,
    select_window_in_session,
)


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
        session_name = get_scope_session()
        window_name = "scope-top"
        scope_env = {"SCOPE_TUI_DETACH_ON_EXIT": "1"}
        scope_cmd = "scope --inside-tmux"
        if dangerously_skip_permissions:
            scope_env["SCOPE_DANGEROUSLY_SKIP_PERMISSIONS"] = "1"
            scope_cmd += " --dangerously-skip-permissions"
        env_prefix = " ".join(f"{k}={v}" for k, v in scope_env.items())
        scope_cmd_with_env = f"{env_prefix} {scope_cmd}"

        if has_session(session_name):
            if has_window_in_session(session_name, window_name):
                if is_window_dead(session_name, window_name):
                    try:
                        kill_window_in_session(session_name, window_name)
                    except TmuxError:
                        pass
                    create_window(
                        name=window_name,
                        command=scope_cmd,
                        env=scope_env,
                    )
            else:
                create_window(
                    name=window_name,
                    command=scope_cmd,
                    env=scope_env,
                )

            try:
                select_window_in_session(session_name, window_name)
            except TmuxError:
                pass

            os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])

        os.execvp(
            "tmux",
            [
                "tmux",
                "new-session",
                "-s",
                session_name,
                "-n",
                window_name,
                scope_cmd_with_env,
            ],
        )
    else:
        # Already in tmux - run the TUI directly
        from scope.tui.app import ScopeApp

        app = ScopeApp(dangerously_skip_permissions=dangerously_skip_permissions)
        app.run()


# Register commands
main.add_command(spawn)
main.add_command(poll)
main.add_command(abort)
main.add_command(setup)
main.add_command(trajectory)
main.add_command(update)
main.add_command(wait)
main.add_command(estimate)
