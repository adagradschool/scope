"""Termination criteria evaluation for feedback loops.

Provides mechanism to check whether an iteration loop should terminate
based on verification criteria results. The orchestrator retains authority
to override recommendations — Scope provides signals, not enforcement.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TerminationCheck:
    """Result of checking a single criterion."""

    criterion: str
    passed: bool
    detail: str = ""


@dataclass
class TerminationResult:
    """Result of evaluating all termination criteria for an iteration."""

    checks: list[TerminationCheck]
    iteration: int
    max_iterations: int
    recommend_terminate: bool
    reason: str

    def summary(self) -> str:
        """Format a human-readable summary of the termination evaluation."""
        parts: list[str] = []

        parts.append(f"Iteration {self.iteration}/{self.max_iterations}")
        parts.append("")

        for check in self.checks:
            status = "PASS" if check.passed else "FAIL"
            line = f"  [{status}] {check.criterion}"
            if check.detail:
                line += f" — {check.detail}"
            parts.append(line)

        parts.append("")
        if self.recommend_terminate:
            parts.append(f"Recommendation: TERMINATE — {self.reason}")
        else:
            parts.append(f"Recommendation: ITERATE — {self.reason}")

        return "\n".join(parts)


def run_criterion(criterion: str, cwd: Path | None = None) -> TerminationCheck:
    """Run a single termination criterion.

    If the criterion looks like a shell command (contains common command
    patterns), it is executed as a subprocess. Otherwise it is treated
    as a descriptive criterion that cannot be automatically checked.

    Args:
        criterion: The criterion string — either a command or description.
        cwd: Working directory for command execution.

    Returns:
        TerminationCheck with pass/fail result.
    """
    if _is_command(criterion):
        return _run_command_criterion(criterion, cwd)
    return TerminationCheck(
        criterion=criterion,
        passed=False,
        detail="descriptive criterion — cannot be automatically verified",
    )


def _is_command(criterion: str) -> bool:
    """Heuristic: does this criterion look like a shell command?"""
    # Common command prefixes and patterns
    command_indicators = [
        "pytest", "ruff", "mypy", "black", "cargo", "npm", "make",
        "go ", "python", "node", "bash", "sh ", "test ", "./",
    ]
    lower = criterion.lower().strip()
    return any(lower.startswith(prefix) for prefix in command_indicators)


def _run_command_criterion(criterion: str, cwd: Path | None = None) -> TerminationCheck:
    """Execute a criterion as a shell command and check exit code."""
    try:
        result = subprocess.run(
            criterion,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cwd,
        )
        passed = result.returncode == 0
        detail = ""
        if not passed:
            # Capture last line of stderr or stdout for context
            output = result.stderr.strip() or result.stdout.strip()
            if output:
                lines = output.splitlines()
                detail = lines[-1][:200]
        return TerminationCheck(criterion=criterion, passed=passed, detail=detail)
    except subprocess.TimeoutExpired:
        return TerminationCheck(
            criterion=criterion, passed=False, detail="command timed out"
        )
    except OSError as e:
        return TerminationCheck(
            criterion=criterion, passed=False, detail=f"execution error: {e}"
        )


def evaluate_termination(
    criteria: list[str],
    iteration: int,
    max_iterations: int,
    cwd: Path | None = None,
) -> TerminationResult:
    """Evaluate termination criteria and produce a recommendation.

    Runs all criteria checks and determines whether to recommend
    termination or continued iteration.

    Args:
        criteria: List of termination criteria (commands or descriptions).
        iteration: Current iteration number (1-based).
        max_iterations: Maximum allowed iterations.
        cwd: Working directory for command execution.

    Returns:
        TerminationResult with checks, recommendation, and reason.
    """
    checks = [run_criterion(c, cwd=cwd) for c in criteria]

    all_passed = all(c.passed for c in checks)
    at_max = iteration >= max_iterations

    if all_passed:
        return TerminationResult(
            checks=checks,
            iteration=iteration,
            max_iterations=max_iterations,
            recommend_terminate=True,
            reason="all criteria passed",
        )

    if at_max:
        failed = [c.criterion for c in checks if not c.passed]
        return TerminationResult(
            checks=checks,
            iteration=iteration,
            max_iterations=max_iterations,
            recommend_terminate=True,
            reason=f"max iterations ({max_iterations}) reached; still failing: {', '.join(failed)}",
        )

    failed = [c.criterion for c in checks if not c.passed]
    return TerminationResult(
        checks=checks,
        iteration=iteration,
        max_iterations=max_iterations,
        recommend_terminate=False,
        reason=f"criteria not met: {', '.join(failed)}",
    )


def load_termination_criteria(session_dir: Path) -> list[str] | None:
    """Load termination criteria from a session directory.

    Args:
        session_dir: Path to the session directory.

    Returns:
        List of criteria strings, or None if not set.
    """
    criteria_file = session_dir / "termination_criteria"
    if not criteria_file.exists():
        return None
    content = criteria_file.read_text().strip()
    if not content:
        return None
    return content.splitlines()


def save_termination_criteria(session_dir: Path, criteria: list[str]) -> None:
    """Save termination criteria to a session directory.

    Args:
        session_dir: Path to the session directory.
        criteria: List of criteria strings.
    """
    (session_dir / "termination_criteria").write_text("\n".join(criteria))


def load_max_iterations(session_dir: Path) -> int:
    """Load max iterations bound from a session directory.

    Args:
        session_dir: Path to the session directory.

    Returns:
        Max iterations value, defaults to 10 if not set.
    """
    max_iter_file = session_dir / "max_iterations"
    if max_iter_file.exists():
        try:
            return int(max_iter_file.read_text().strip())
        except ValueError:
            pass
    return 10


def save_max_iterations(session_dir: Path, max_iterations: int) -> None:
    """Save max iterations bound to a session directory.

    Args:
        session_dir: Path to the session directory.
        max_iterations: Maximum iteration count.
    """
    (session_dir / "max_iterations").write_text(str(max_iterations))


def load_iteration_count(session_dir: Path) -> int:
    """Load current iteration count from a session directory.

    Args:
        session_dir: Path to the session directory.

    Returns:
        Current iteration count, defaults to 0 if not set.
    """
    iter_file = session_dir / "iteration"
    if iter_file.exists():
        try:
            return int(iter_file.read_text().strip())
        except ValueError:
            pass
    return 0


def save_iteration_count(session_dir: Path, iteration: int) -> None:
    """Save current iteration count to a session directory.

    Args:
        session_dir: Path to the session directory.
        iteration: Current iteration number.
    """
    (session_dir / "iteration").write_text(str(iteration))
