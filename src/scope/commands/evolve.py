"""Evolution commands for scope skill improvement.

Provides CLI subcommands to run evolution cycles, inspect candidates,
apply or reject mutations, and manage skill versions.
"""

import click
import orjson

from scope.core.evolve import (
    apply_candidate,
    get_active_version,
    get_evolution_dir,
    list_staged,
    list_versions,
    pareto_select,
    reject_candidate,
    rollback,
    run_evolution,
)
from scope.core.project import get_project_identifier


@click.group()
def evolve():
    """Skill evolution - critique, mutate, and improve the scope skill."""
    pass


@evolve.command("run")
@click.option(
    "--session", required=True, help="Completed loop session ID to evolve against."
)
@click.option(
    "--project", default="", help="Project identifier (auto-detected if omitted)."
)
def evolve_run(session, project):
    """Run evolution against a completed loop session."""
    try:
        project_id = project or get_project_identifier()
        candidate_id = run_evolution(session, project_id)
        click.echo(candidate_id)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@evolve.command("status")
def evolve_status():
    """Show all staged candidates, highlighting Pareto front."""
    try:
        candidates = list_staged()
        if not candidates:
            click.echo("No staged candidates.")
            return

        # Determine which candidates are on the Pareto front
        scored = [c for c in candidates if c.get("scores")]
        pareto = pareto_select(scored) if scored else []
        pareto_ids = {c["candidate_id"] for c in pareto}

        # Print header
        click.echo(
            f"{'CANDIDATE':<20} {'CREATED':<22} {'SESSION':<14} {'SCORE':>7} {'PARETO':<6}"
        )
        click.echo("-" * 75)

        for c in candidates:
            cid = c.get("candidate_id", "?")
            created = c.get("created_at", "?")[:19]
            session_id = c.get("loop_session_id", "?")
            scores = c.get("scores", {})
            overall = sum(scores.values()) / len(scores) if scores else 0.0
            is_pareto = cid in pareto_ids

            line = f"{cid:<20} {created:<22} {session_id:<14} {overall:>6.2f} "
            if is_pareto:
                line += click.style("yes", fg="green")
            else:
                line += "no"
            click.echo(line)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@evolve.command("diff")
@click.argument("candidate_id", required=False)
def evolve_diff(candidate_id):
    """Show unified diff for a candidate.

    If no CANDIDATE_ID is given, picks the best Pareto candidate.
    """
    try:
        if not candidate_id:
            candidates = list_staged()
            scored = [c for c in candidates if c.get("scores")]
            pareto = pareto_select(scored) if scored else []
            if not pareto:
                click.echo("No scored candidates available.", err=True)
                raise SystemExit(1)
            # Pick highest overall score
            best = max(
                pareto,
                key=lambda c: sum(c.get("scores", {}).values())
                / max(len(c.get("scores", {})), 1),
            )
            candidate_id = best["candidate_id"]
            click.echo(f"Showing diff for best Pareto candidate: {candidate_id}")

        diff_path = get_evolution_dir() / "staged" / candidate_id / "diff.patch"
        if not diff_path.exists():
            click.echo(f"Error: no diff found for candidate {candidate_id}", err=True)
            raise SystemExit(1)

        click.echo(diff_path.read_text())
    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@evolve.command("apply")
@click.argument("candidate_id")
def evolve_apply(candidate_id):
    """Apply a staged candidate as a new skill version."""
    try:
        apply_candidate(candidate_id)
        active = get_active_version()
        click.echo(f"Applied {candidate_id} as {click.style(active, fg='green')}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@evolve.command("reject")
@click.argument("candidate_id")
def evolve_reject(candidate_id):
    """Reject and remove a staged candidate."""
    try:
        reject_candidate(candidate_id)
        click.echo(f"Rejected candidate {candidate_id}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@evolve.command("rollback")
@click.argument("version_id")
def evolve_rollback(version_id):
    """Rollback to a specific skill version."""
    try:
        rollback(version_id)
        click.echo(f"Rolled back to {click.style(version_id, fg='yellow')}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@evolve.command("history")
def evolve_history():
    """Show evolution event log."""
    try:
        history_path = get_evolution_dir() / "history.jsonl"
        if not history_path.exists():
            click.echo("No evolution history yet.")
            return

        for line in history_path.read_bytes().splitlines():
            if not line.strip():
                continue
            event = orjson.loads(line)
            ts = event.get("timestamp", "?")[:19]
            etype = event.get("event", "?")
            # Build details from remaining keys
            details = {
                k: v for k, v in event.items() if k not in ("timestamp", "event")
            }
            detail_str = ", ".join(f"{k}={v}" for k, v in details.items())
            click.echo(f"{ts}  {etype:<12} {detail_str}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@evolve.command("versions")
def evolve_versions():
    """List all skill versions."""
    try:
        versions = list_versions()
        if not versions:
            click.echo("No versions found.")
            return

        active = get_active_version()

        click.echo(
            f"{'':>2} {'VERSION':<10} {'CREATED':<22} {'SOURCE':<14} {'PARENT':<10}"
        )
        click.echo("-" * 60)

        for v in versions:
            vid = v.get("version", "?")
            created = v.get("created_at", "?")[:19]
            source = v.get("source", "?")
            parent = v.get("parent", "-")
            marker = click.style("*", fg="green") if vid == active else " "
            click.echo(f"{marker:>2} {vid:<10} {created:<22} {source:<14} {parent:<10}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
