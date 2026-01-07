"""Trajectory command for scope.

View the conversation trajectory for a session.
"""

import click
import orjson

from scope.core.state import (
    has_trajectory,
    load_trajectory,
    load_trajectory_index,
    resolve_id,
)


@click.command()
@click.argument("session_id")
@click.option("--full", is_flag=True, help="Show full trajectory (pretty-printed)")
@click.option(
    "--json", "output_json", is_flag=True, help="Output full trajectory as raw JSONL"
)
def trajectory(session_id: str, full: bool, output_json: bool) -> None:
    """View conversation trajectory for a session.

    By default, shows a compact summary (turn count, tools used, duration).
    Use --full or --json to see the complete trajectory.

    SESSION_ID is the ID or alias of the session.

    Examples:

        scope trajectory 0            # Summary (default)

        scope trajectory 0 --full     # Pretty-printed full trajectory

        scope trajectory 0 --json     # Raw JSONL output
    """
    resolved_id = resolve_id(session_id)
    if resolved_id is None:
        click.echo(f"Session {session_id} not found", err=True)
        raise SystemExit(1)

    if not has_trajectory(resolved_id):
        click.echo(f"No trajectory found for session {resolved_id}", err=True)
        raise SystemExit(1)

    # Default: show summary
    if not full and not output_json:
        index = load_trajectory_index(resolved_id)
        if index is None:
            click.echo(f"No trajectory index found for session {resolved_id}", err=True)
            raise SystemExit(1)
        click.echo(orjson.dumps(index, option=orjson.OPT_INDENT_2).decode())
        return

    entries = load_trajectory(resolved_id)
    if entries is None:
        click.echo(f"Failed to load trajectory for session {resolved_id}", err=True)
        raise SystemExit(1)

    if output_json:
        # Output raw JSONL
        for entry in entries:
            click.echo(orjson.dumps(entry).decode())
        return

    # Pretty-print: show turns and tool calls
    for entry in entries:
        _pretty_print_entry(entry)


def _pretty_print_entry(entry: dict) -> None:
    """Pretty-print a single trajectory entry."""
    entry_type = entry.get("type", "unknown")

    if entry_type == "user":
        content = entry.get("content", "")
        click.secho("USER:", fg="cyan", bold=True)
        click.echo(f"  {_truncate(content, 200)}")
        click.echo()

    elif entry_type == "assistant":
        click.secho("ASSISTANT:", fg="green", bold=True)
        content = entry.get("content", "")
        if content:
            click.echo(f"  {_truncate(content, 200)}")

        # Show tool calls if present
        tool_calls = entry.get("tool_calls", [])
        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "unknown")
            click.secho(f"  TOOL: {tool_name}", fg="yellow")

            # Show brief input summary
            tool_input = tool_call.get("input", {})
            if isinstance(tool_input, dict):
                for key, value in list(tool_input.items())[:3]:
                    value_str = str(value)
                    click.echo(f"    {key}: {_truncate(value_str, 80)}")
        click.echo()

    elif entry_type == "tool_result":
        tool_name = entry.get("tool_name", "unknown")
        click.secho(f"RESULT ({tool_name}):", fg="magenta")
        result = entry.get("result", "")
        click.echo(f"  {_truncate(str(result), 150)}")
        click.echo()

    else:
        # Unknown entry type, just dump it
        click.secho(f"[{entry_type}]", fg="white", dim=True)
        click.echo(f"  {_truncate(str(entry), 100)}")
        click.echo()


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
