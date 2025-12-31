"""Top command - launch the scope TUI."""

import os

import click
from scope.core.tmux import (
    TmuxError,
    create_window,
    get_current_session,
    get_scope_session,
    has_session,
    has_window_in_session,
    is_window_dead,
    kill_window_in_session,
    select_window_in_session,
)


@click.command()
@click.option(
    "--dangerously-skip-permissions",
    is_flag=True,
    envvar="SCOPE_DANGEROUSLY_SKIP_PERMISSIONS",
    help="Pass --dangerously-skip-permissions to spawned Claude instances",
)
def top(dangerously_skip_permissions: bool) -> None:
    """Launch the scope TUI.

    Shows all sessions and auto-refreshes on changes.
    If not running inside tmux, automatically starts tmux first.
    """
    # If not in tmux, exec into tmux running scope top
    if get_current_session() is None:
        session_name = get_scope_session()
        window_name = "scope-top"
        scope_env = {"SCOPE_TUI_DETACH_ON_EXIT": "1"}
        scope_cmd = "scope top"
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

    from scope.tui.app import ScopeApp

    app = ScopeApp(dangerously_skip_permissions=dangerously_skip_permissions)
    app.run()
