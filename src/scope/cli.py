"""CLI entry point for scope.

Usage:
    scope spawn "task description"
    scope poll <id>
    scope top
"""

import click

from scope.commands.poll import poll
from scope.commands.spawn import spawn
from scope.commands.top import top


@click.group()
@click.version_option()
def main() -> None:
    """Scope - Subagent orchestration for Claude Code.

    Spawn bounded, purpose-specific subagents. Preserve your context.
    Maintain visibility and control.
    """
    pass


# Register commands
main.add_command(spawn)
main.add_command(poll)
main.add_command(top)
