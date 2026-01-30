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

from dataclasses import dataclass, field

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

        Returns:
            Dict mapping phase name to PhaseResult.
        """
        raise NotImplementedError(
            "Workflow execution requires scope spawn integration — coming soon"
        )
