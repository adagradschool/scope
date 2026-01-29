"""Uninstall command for scope.

Completely removes scope from the system, including:
- ~/.scope directory (all session data)
- Scope hooks from Claude Code settings
- Scope skills from ~/.claude/skills/
- ccstatusline configuration added by scope
- tmux hooks installed by scope
"""

import shutil
import sys
from pathlib import Path

import click

from scope.hooks.install import (
    get_claude_settings_path,
    get_claude_skills_dir,
    uninstall_hooks,
    uninstall_tmux_hooks,
)

# List of scope skills to remove
SCOPE_SKILLS = ["scope", "ralph", "tdd", "rlm", "map-reduce", "maker-checker", "dag"]


def get_scope_data_dir() -> Path:
    """Get the path to scope's data directory."""
    return Path.home() / ".scope"


def uninstall_skills() -> int:
    """Remove scope-installed skills from ~/.claude/skills/.

    Only removes skills that were installed by scope (ralph, tdd, rlm, etc.).
    Preserves any user-installed skills.

    Returns:
        Number of skills removed.
    """
    skills_dir = get_claude_skills_dir()
    removed = 0

    for skill_name in SCOPE_SKILLS:
        skill_dir = skills_dir / skill_name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            removed += 1

    return removed


def uninstall_ccstatusline() -> bool:
    """Remove statusLine configuration added by scope from Claude settings.

    Only removes the statusLine setting if it references ccstatusline.
    Does NOT remove ~/.config/ccstatusline/ as that may be user-configured.

    Returns:
        True if statusLine was removed, False otherwise.
    """
    import orjson

    settings_path = get_claude_settings_path()

    if not settings_path.exists():
        return False

    content = settings_path.read_bytes()
    if not content:
        return False

    settings = orjson.loads(content)

    # Only remove if it's the ccstatusline config we installed
    status_line = settings.get("statusLine", {})
    if isinstance(status_line, dict):
        command = status_line.get("command", "")
        if "ccstatusline" in command:
            del settings["statusLine"]
            settings_path.write_bytes(
                orjson.dumps(settings, option=orjson.OPT_INDENT_2)
            )
            return True

    return False


def find_scope_binaries() -> list[Path]:
    """Find scope and scope-hook binaries in common locations.

    Returns:
        List of paths to scope binaries found.
    """
    binaries = []
    binary_names = ["scope", "scope-hook"]

    # Check common installation locations
    search_paths = [
        Path.home() / ".local" / "bin",
        Path("/usr/local/bin"),
        Path("/usr/bin"),
    ]

    # Also check PATH entries
    path_env = sys.prefix
    if path_env:
        search_paths.append(Path(path_env) / "bin")

    for search_path in search_paths:
        for binary_name in binary_names:
            binary_path = search_path / binary_name
            if binary_path.exists():
                binaries.append(binary_path)

    return binaries


def remove_scope_data() -> bool:
    """Remove ~/.scope directory.

    Returns:
        True if directory was removed, False if it didn't exist.
    """
    scope_dir = get_scope_data_dir()

    if scope_dir.exists():
        shutil.rmtree(scope_dir)
        return True

    return False


@click.command()
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.option(
    "--keep-data",
    is_flag=True,
    help="Keep ~/.scope session data (only remove hooks and skills)",
)
def uninstall(yes: bool, keep_data: bool) -> None:
    """Completely remove scope from your system.

    This command removes all traces of scope:

    \b
    1. Removes scope hooks from ~/.claude/settings.json
    2. Removes scope skills from ~/.claude/skills/ (ralph, tdd, rlm, etc.)
    3. Removes statusLine config if it uses ccstatusline
    4. Removes tmux pane-died hook
    5. Removes ~/.scope directory (unless --keep-data)

    User hooks and skills are preserved.

    To reinstall scope later, run: pip install scopeai && scope setup

    Examples:

        scope uninstall           # Interactive confirmation
        scope uninstall -y        # Skip confirmation
        scope uninstall --keep-data  # Keep session history
    """
    click.echo("Scope Uninstaller")
    click.echo("=" * 40)
    click.echo()

    # Show what will be removed
    click.echo("This will remove:")
    click.echo("  - Scope hooks from Claude Code settings")
    click.echo(
        "  - Scope skills (scope, ralph, tdd, rlm, map-reduce, maker-checker, dag)"
    )
    click.echo("  - ccstatusline status bar configuration")
    click.echo("  - tmux pane-died hook")

    if not keep_data:
        scope_dir = get_scope_data_dir()
        if scope_dir.exists():
            click.echo(f"  - Session data in {scope_dir}")

    click.echo()
    click.echo("User hooks and skills will be preserved.")
    click.echo()

    # Find binaries
    binaries = find_scope_binaries()
    if binaries:
        click.echo("Note: The following binaries were found but will NOT be removed")
        click.echo("automatically (uninstall with pip):")
        for binary in binaries:
            click.echo(f"  - {binary}")
        click.echo()
        click.echo("To fully remove, run: pip uninstall scopeai")
        click.echo()

    if not yes:
        if not click.confirm("Proceed with uninstall?"):
            click.echo("Uninstall cancelled.")
            raise SystemExit(0)

    click.echo()

    # 1. Remove Claude Code hooks
    click.echo("Removing scope hooks from Claude Code settings...")
    uninstall_hooks()
    click.echo("  Done.")

    # 2. Remove skills
    click.echo("Removing scope skills...")
    skills_removed = uninstall_skills()
    click.echo(f"  Removed {skills_removed} skills.")

    # 3. Remove ccstatusline config
    click.echo("Removing ccstatusline configuration...")
    if uninstall_ccstatusline():
        click.echo("  Removed statusLine from Claude settings.")
    else:
        click.echo("  No ccstatusline config found (or not installed by scope).")

    # 4. Remove tmux hooks
    click.echo("Removing tmux hooks...")
    uninstall_tmux_hooks()
    click.echo("  Done.")

    # 5. Remove data directory
    if not keep_data:
        click.echo("Removing scope data directory...")
        if remove_scope_data():
            click.echo("  Removed ~/.scope")
        else:
            click.echo("  ~/.scope did not exist.")

    click.echo()
    click.echo("Scope has been uninstalled.")

    if binaries:
        click.echo()
        click.echo("Remember to run 'pip uninstall scopeai' to remove the package.")
