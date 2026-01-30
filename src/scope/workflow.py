"""Workflow builder for scope.

Sequences multiple doer-checker loops (phases) into a pipeline.
Each phase runs sequentially; results pipe forward automatically.

Usage:
    from scope import Workflow

    wf = Workflow("tdd")
    wf.phase("red", task="Write failing tests", checker="pytest tests/")
    wf.phase("green", task="Make tests pass", checker="pytest tests/", max_iterations=5)
    wf.phase("refactor", task="Refactor for clarity", checker="agent: Review. ACCEPT/RETRY")
    results = wf.run()
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import click

from scope.core.loop import LoopResult


@dataclass
class PhaseResult:
    """Result of a single workflow phase."""

    phase_name: str
    loop_result: LoopResult
    passed: bool

    @property
    def result_text(self) -> str:
        return self.loop_result.result_text

    @property
    def verdict(self) -> str:
        return self.loop_result.verdict

    @property
    def exit_reason(self) -> str:
        return self.loop_result.exit_reason


@dataclass
class Phase:
    """Definition of a workflow phase."""

    name: str
    task: str
    checker: str
    max_iterations: int = 3
    checker_model: str = ""
    model: str = ""
    on_fail: str = "stop"  # "stop" | "continue" | "retry:N"
    pipe_from: list[str] = field(default_factory=list)
    file_scope: list[str] | None = None
    verify: list[str] | None = None
    result: PhaseResult | None = None


class Workflow:
    """Builder for multi-phase doer-checker workflows.

    Phases run sequentially. By default, each phase receives the result
    of the immediately preceding phase as context. Use pipe_from= to override.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.phases: list[Phase] = []
        self._phase_names: set[str] = set()

    def phase(
        self,
        name: str,
        *,
        task: str,
        checker: str,
        max_iterations: int = 3,
        checker_model: str = "",
        model: str = "",
        on_fail: str = "stop",
        pipe_from: list[str] | None = None,
        file_scope: list[str] | None = None,
        verify: list[str] | None = None,
    ) -> Phase:
        """Register a new phase.

        Args:
            name: Unique phase name.
            task: Prompt/task for the doer.
            checker: Checker specification (command or "agent:..." prompt).
            max_iterations: Max doer-checker iterations.
            checker_model: Model for agent checker.
            model: Model for the doer.
            on_fail: What to do on failure: "stop", "continue", or "retry:N".
            pipe_from: Phase names to pipe results from. None = no explicit pipe.
            file_scope: Files relevant to this phase.
            verify: Verification commands to run.

        Returns:
            The registered Phase object.
        """
        if name in self._phase_names:
            raise ValueError(f"Duplicate phase name: {name}")

        if pipe_from is not None:
            for source in pipe_from:
                if source not in self._phase_names:
                    raise ValueError(
                        f"Phase '{name}' pipes from unknown phase '{source}'"
                    )

        p = Phase(
            name=name,
            task=task,
            checker=checker,
            max_iterations=max_iterations,
            checker_model=checker_model,
            model=model,
            on_fail=on_fail,
            pipe_from=pipe_from if pipe_from is not None else [],
            file_scope=file_scope,
            verify=verify,
        )
        self.phases.append(p)
        self._phase_names.add(name)
        return p

    def run(self) -> dict[str, PhaseResult]:
        """Execute all phases sequentially.

        Each phase spawns a ``scope spawn`` subprocess that runs a full
        doer-checker loop.  Results from prior phases are piped forward
        as context (by default from the immediately preceding phase, or
        from explicit ``pipe_from`` sources).

        Returns:
            Dict mapping phase name to PhaseResult.
        """
        if not self.phases:
            return {}

        results: dict[str, PhaseResult] = {}

        for i, phase in enumerate(self.phases):
            click.echo(
                f"\n{'=' * 60}\n"
                f"Workflow '{self.name}' — Phase: {phase.name}\n"
                f"{'=' * 60}\n",
                err=True,
            )

            # Build enriched task prompt
            task = _build_phase_task(phase, i, self.phases, results)

            # Build spawn command
            cmd = [
                "scope",
                "spawn",
                task,
                "--checker",
                phase.checker,
                "--max-iterations",
                str(phase.max_iterations),
            ]
            if phase.model:
                cmd.extend(["--model", phase.model])
            if phase.checker_model:
                cmd.extend(["--checker-model", phase.checker_model])

            # Run spawn (blocks until the loop completes)
            proc = subprocess.run(cmd, capture_output=True, text=True)
            session_id = (
                proc.stdout.strip().split("\n")[0] if proc.stdout.strip() else ""
            )

            loop_result = _read_loop_result(session_id, phase)
            passed = loop_result.verdict == "accept"
            phase_result = PhaseResult(
                phase_name=phase.name,
                loop_result=loop_result,
                passed=passed,
            )
            phase.result = phase_result
            results[phase.name] = phase_result

            if passed:
                click.echo(f"Phase '{phase.name}' passed.", err=True)
            elif phase.on_fail == "continue":
                click.echo(
                    f"Phase '{phase.name}' failed "
                    f"(verdict: {loop_result.verdict}). Continuing.",
                    err=True,
                )
            else:
                # on_fail == "stop" (default)
                click.echo(
                    f"Phase '{phase.name}' failed "
                    f"(verdict: {loop_result.verdict}). Stopping workflow.",
                    err=True,
                )
                break

        return results


def _build_phase_task(
    phase: Phase,
    index: int,
    phases: list[Phase],
    results: dict[str, PhaseResult],
) -> str:
    """Assemble the full task prompt for a phase, including piped context."""
    sections: list[str] = [phase.task]

    # Collect piped results
    prior_texts = _collect_prior_results(phase, index, phases, results)
    if prior_texts:
        body = "\n\n---\n\n".join(prior_texts)
        sections.append(f"# Prior Phase Results\n\n{body}")

    if phase.file_scope:
        constraints = "\n".join(f"- `{p}`" for p in phase.file_scope)
        sections.append(
            f"# File Scope\n\nOnly modify files within:\n{constraints}"
        )

    if phase.verify:
        checks = "\n".join(f"- {v}" for v in phase.verify)
        sections.append(
            f"# Verification\n\nYour output will be verified against:\n{checks}"
        )

    return "\n\n".join(sections)


def _collect_prior_results(
    phase: Phase,
    index: int,
    phases: list[Phase],
    results: dict[str, PhaseResult],
) -> list[str]:
    """Gather result texts from prior phases for piping."""
    prior: list[str] = []

    if phase.pipe_from:
        # Explicit pipe sources
        for source_name in phase.pipe_from:
            if source_name in results and results[source_name].result_text:
                prior.append(
                    f"**{source_name}**: {results[source_name].result_text}"
                )
    elif index > 0:
        # Default: pipe from immediately preceding phase
        prev_name = phases[index - 1].name
        if prev_name in results and results[prev_name].result_text:
            prior.append(
                f"**{prev_name}**: {results[prev_name].result_text}"
            )

    return prior


def _read_loop_result(session_id: str, phase: Phase) -> LoopResult:
    """Reconstruct a LoopResult from persisted session state."""
    if not session_id:
        return LoopResult(
            session_id="",
            verdict="terminate",
            iterations=0,
            result_text="spawn failed",
        )

    from scope.core.state import (
        ensure_scope_dir,
        load_exit_reason,
        load_loop_state,
        load_session,
    )

    scope_dir = ensure_scope_dir()
    session_dir = scope_dir / "sessions" / session_id

    # Read result text
    result_file = session_dir / "result"
    result_text = result_file.read_text().strip() if result_file.exists() else ""

    # Read loop state
    loop_state = load_loop_state(session_id)
    history = loop_state.get("history", []) if loop_state else []
    max_iterations = (
        loop_state.get("max_iterations", phase.max_iterations)
        if loop_state
        else phase.max_iterations
    )

    # Check for exit
    session = load_session(session_id)
    if session and session.state == "exited":
        return LoopResult(
            session_id=session_id,
            verdict="exit",
            iterations=len(history),
            history=history,
            result_text=result_text,
            exit_reason=load_exit_reason(session_id) or "",
        )

    # Check for abort / failure
    if session and session.state in {"aborted", "failed"}:
        return LoopResult(
            session_id=session_id,
            verdict="terminate",
            iterations=len(history),
            history=history,
            result_text=result_text,
        )

    # Determine verdict from history
    if history:
        last_verdict = history[-1].get("verdict", "retry")
        if last_verdict == "accept":
            verdict = "accept"
        elif last_verdict == "terminate":
            verdict = "terminate"
        else:
            # Last verdict was "retry" but loop ended — hit max_iterations
            verdict = "max_iterations"
    else:
        # No history at all — session completed without any checker run
        verdict = "max_iterations"

    return LoopResult(
        session_id=session_id,
        verdict=verdict,
        iterations=len(history) or 1,
        history=history,
        result_text=result_text,
    )
