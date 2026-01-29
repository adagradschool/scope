"""Verification infrastructure for scope sessions.

Runs configurable verification commands (tests, lint, type checks) against the
working tree after a sub-agent completes and returns structured results.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VerifyStep:
    """A single verification command to run."""

    name: str
    command: str


@dataclass
class StepResult:
    """Result of running a single verification step."""

    name: str
    passed: bool
    output: str


@dataclass
class VerifyResult:
    """Aggregate result of all verification steps."""

    steps: list[StepResult] = field(default_factory=list)
    passed: bool = True
    summary: str = ""


def run_verification(
    steps: list[VerifyStep],
    cwd: Path,
    timeout: int = 300,
) -> VerifyResult:
    """Run verification steps and return structured results.

    Args:
        steps: List of verification steps to run.
        cwd: Working directory for commands.
        timeout: Per-command timeout in seconds.

    Returns:
        VerifyResult with per-step results and overall summary.
    """
    result = VerifyResult()

    for step in steps:
        try:
            proc = subprocess.run(
                step.command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            passed = proc.returncode == 0
            output = proc.stdout
            if proc.stderr:
                output = output + proc.stderr if output else proc.stderr
        except subprocess.TimeoutExpired:
            passed = False
            output = f"Command timed out after {timeout}s"
        except OSError as e:
            passed = False
            output = f"Command failed to start: {e}"

        result.steps.append(StepResult(name=step.name, passed=passed, output=output))
        if not passed:
            result.passed = False

    # Build summary
    parts = []
    for sr in result.steps:
        status = "passed" if sr.passed else "FAILED"
        parts.append(f"{sr.name} {status}")
    result.summary = ", ".join(parts)

    return result
