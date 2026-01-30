"""Loop engine for scope.

Extracted from spawn.py — the doer→checker loop as a reusable module.
"""

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import click
from watchfiles import watch

from scope.core.contract import generate_checker_contract
from scope.core.state import (
    ensure_scope_dir,
    load_exit_reason,
    load_session,
    save_loop_state,
)
from scope.core.tmux import send_keys

TERMINAL_STATES = {"done", "aborted", "failed", "exited"}
CONTRACT_CHUNK_SIZE = 2000
PENDING_TASK = "(pending...)"


@dataclass
class LoopResult:
    """Result of a doer→checker loop execution."""

    session_id: str
    verdict: str  # "accept" | "terminate" | "max_iterations" | "exit"
    iterations: int
    history: list[dict] = field(default_factory=list)
    result_text: str = ""
    exit_reason: str = ""


def wait_for_sessions(session_ids: list[str]) -> None:
    """Block until all given sessions reach a terminal state."""
    scope_dir = ensure_scope_dir()
    pending: dict[str, Path] = {}
    for sid in session_ids:
        session = load_session(sid)
        if session is None:
            continue
        if session.state in TERMINAL_STATES:
            continue
        pending[sid] = scope_dir / "sessions" / sid

    if not pending:
        return

    watch_paths = list(pending.values())
    for changes in watch(*watch_paths):
        for _, changed_path in changes:
            changed_path = Path(changed_path)
            if changed_path.name == "state":
                sid = changed_path.parent.name
                if sid in pending:
                    session = load_session(sid)
                    if session and session.state in TERMINAL_STATES:
                        del pending[sid]
        if not pending:
            return


def read_result(scope_dir: Path, session_id: str) -> str:
    """Read the result file for a completed session."""
    result_file = scope_dir / "sessions" / session_id / "result"
    if result_file.exists():
        return result_file.read_text().strip()
    return ""


def parse_verdict(response: str) -> tuple[str, str]:
    """Parse a verdict from an agent checker's response.

    Scans for ACCEPT, RETRY, or TERMINATE in the response.
    The feedback is the full response text.

    Returns:
        Tuple of (verdict, feedback).
    """
    # Check for verdicts — scan from the end (most likely location)
    # Priority: TERMINATE > ACCEPT > RETRY (TERMINATE is most specific)
    lines_reversed = response.strip().split("\n")[::-1]

    for line in lines_reversed:
        line_upper = line.upper().strip()
        if "TERMINATE" in line_upper:
            return ("terminate", response)
        if "ACCEPT" in line_upper:
            return ("accept", response)
        if "RETRY" in line_upper:
            return ("retry", response)

    # No verdict found — default to retry with the full response as feedback
    return ("retry", response)


def spawn_session(
    prompt: str,
    model: str = "",
    dangerously_skip_permissions: bool = False,
    parent_session_id: str = "",
) -> str:
    """Spawn a scope session as a tmux window.

    Shared helper for spawning both retry doers and checker sessions
    inside the loop. Each becomes a real tmux window you can introspect
    and steer.

    Returns the new session ID.
    """
    cmd = ["scope", "spawn", prompt]
    if model:
        cmd.extend(["--model", model])
    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    # Inner sessions use a trivial checker — the outer loop is the
    # real verification mechanism.
    cmd.extend(["--checker", "true"])

    env = os.environ.copy()
    if parent_session_id:
        env["SCOPE_SESSION_ID"] = parent_session_id
    # Inner spawns must not themselves run a loop
    env["SCOPE_SKIP_LOOP"] = "1"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        if result.returncode != 0:
            click.echo(
                f"Loop: failed to spawn session: {result.stderr.strip()}",
                err=True,
            )
            raise SystemExit(1)

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        click.echo("Loop: session spawn timed out", err=True)
        raise SystemExit(1)


def send_contract(target: str, contract: str) -> None:
    """Send a contract to Claude Code, chunking if it is large."""
    if len(contract) <= CONTRACT_CHUNK_SIZE:
        send_keys(target, contract)
        return

    for offset in range(0, len(contract), CONTRACT_CHUNK_SIZE):
        chunk = contract[offset : offset + CONTRACT_CHUNK_SIZE]
        send_keys(target, chunk, submit=False, verify=False)
        time.sleep(0.02)
    # Allow the client to process the paste before submitting.
    time.sleep(min(2.0, max(0.2, len(contract) / 5000)))
    send_keys(target, "", submit=True, verify=False)


def run_command_checker(command: str) -> tuple[str, str]:
    """Run a command checker as a subprocess.

    Exit 0 = accept, non-zero = retry with stdout+stderr as feedback.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=Path.cwd(),
        )

        if result.returncode == 0:
            return ("accept", result.stdout.strip())
        else:
            feedback_parts = []
            if result.stdout.strip():
                feedback_parts.append(result.stdout.strip())
            if result.stderr.strip():
                feedback_parts.append(result.stderr.strip())
            feedback = (
                "\n".join(feedback_parts)
                or f"Command exited with code {result.returncode}"
            )
            return ("retry", feedback)

    except subprocess.TimeoutExpired:
        return ("retry", "Checker command timed out after 300 seconds")
    except OSError as e:
        return ("terminate", f"Checker command failed to execute: {e}")


def run_agent_checker(
    checker_prompt: str,
    doer_result: str,
    iteration: int,
    history: list[dict],
    checker_model: str,
    dangerously_skip_permissions: bool,
    parent_session_id: str = "",
) -> tuple[str, str, str]:
    """Run an agent checker as a tmux session.

    Spawns a full scope session with the checker contract so it's
    visible and steerable in tmux, then waits for it to complete.
    """
    contract = generate_checker_contract(
        checker_prompt=checker_prompt,
        doer_result=doer_result,
        iteration=iteration,
        history=history if history else None,
    )

    checker_id = spawn_session(
        prompt=contract,
        model=checker_model,
        dangerously_skip_permissions=dangerously_skip_permissions,
        parent_session_id=parent_session_id,
    )

    # Wait for checker session to finish
    wait_for_sessions([checker_id])

    # Read checker result
    scope_dir = ensure_scope_dir()
    session = load_session(checker_id)
    if session and session.state in {"aborted", "failed", "exited"}:
        return (
            "retry",
            f"Checker session {checker_id} ended with state '{session.state}'",
            checker_id,
        )

    response = read_result(scope_dir, checker_id)
    if not response:
        return ("retry", f"Checker session {checker_id} produced no output", checker_id)

    verdict, feedback = parse_verdict(response)
    return (verdict, feedback, checker_id)


def run_checker(
    checker: str,
    doer_result: str,
    iteration: int,
    history: list[dict],
    checker_model: str,
    dangerously_skip_permissions: bool,
    parent_session_id: str = "",
) -> tuple[str, str, str]:
    """Run the checker and return (verdict, feedback, checker_session_id).

    Command checker: runs as subprocess, exit 0 = accept, non-zero = retry.
    Agent checker (prefix "agent:"): spawns a tmux session to evaluate.

    Returns:
        Tuple of (verdict, feedback, checker_session_id).
        checker_session_id is empty for command checkers.
    """
    if checker.startswith("agent:"):
        return run_agent_checker(
            checker_prompt=checker[len("agent:") :].strip(),
            doer_result=doer_result,
            iteration=iteration,
            history=history,
            checker_model=checker_model,
            dangerously_skip_permissions=dangerously_skip_permissions,
            parent_session_id=parent_session_id,
        )
    else:
        verdict, feedback = run_command_checker(command=checker)
        return (verdict, feedback, "")


def run_loop(
    session_id: str,
    prompt: str,
    checker: str,
    max_iterations: int,
    checker_model: str,
    dangerously_skip_permissions: bool,
) -> LoopResult:
    """Execute the doer->checker loop.

    Waits for the doer to complete, runs the checker, and either accepts
    or retries with feedback up to max_iterations times.

    Returns a LoopResult with the final verdict and history.
    """
    scope_dir = ensure_scope_dir()
    history: list[dict] = []
    current_doer_id = session_id

    for iteration in range(max_iterations):
        # Wait for current doer to complete
        wait_for_sessions([current_doer_id])

        # Read doer result and produce a summary for downstream consumers
        doer_result = read_result(scope_dir, current_doer_id)

        # Check if doer failed/aborted — no point running checker
        session = load_session(current_doer_id)
        if session and session.state in {"aborted", "failed"}:
            click.echo(
                f"Loop: doer session {current_doer_id} ended with state '{session.state}' "
                f"at iteration {iteration}. Terminating loop.",
                err=True,
            )
            return LoopResult(
                session_id=session_id,
                verdict="terminate",
                iterations=iteration + 1,
                history=history,
                result_text=doer_result,
            )

        if session and session.state == "exited":
            reason = load_exit_reason(current_doer_id) or ""
            click.echo(
                f"Loop: doer session {current_doer_id} exited "
                f"at iteration {iteration}: {reason}",
                err=True,
            )
            return LoopResult(
                session_id=session_id,
                verdict="exit",
                iterations=iteration + 1,
                history=history,
                result_text=doer_result,
                exit_reason=reason,
            )

        from scope.core.summarize import summarize

        task_name = session.task if session and session.task else prompt[:80]
        doer_summary = summarize(
            f"Task: {task_name}\n\nResult:\n{doer_result[:2000]}\n\nSummary:",
            goal=(
                "You are a progress summarizer. Given a task and its result, output a 1-2 sentence "
                "summary of what was accomplished and what is left to do. Be specific and concise. "
                "No quotes, no markdown."
            ),
            max_length=300,
            fallback=doer_result[:300] if doer_result else task_name,
        )

        # Run checker with summarized result
        verdict, feedback, checker_session_id = run_checker(
            checker=checker,
            doer_result=doer_summary,
            iteration=iteration,
            history=history,
            checker_model=checker_model,
            dangerously_skip_permissions=dangerously_skip_permissions,
            parent_session_id=session_id,
        )

        # Record history
        entry: dict = {
            "iteration": iteration,
            "doer_session": current_doer_id,
            "verdict": verdict,
            "feedback": feedback,
        }
        if checker_session_id:
            entry["checker_session"] = checker_session_id
        history.append(entry)

        # Persist loop state
        save_loop_state(
            session_id=session_id,
            checker=checker,
            max_iterations=max_iterations,
            current_iteration=iteration,
            history=history,
        )

        if verdict == "accept":
            click.echo(
                f"Loop: checker accepted at iteration {iteration}.",
                err=True,
            )
            return LoopResult(
                session_id=session_id,
                verdict="accept",
                iterations=iteration + 1,
                history=history,
                result_text=doer_result,
            )

        if verdict == "terminate":
            click.echo(
                f"Loop: checker terminated at iteration {iteration}. "
                f"Feedback: {feedback}",
                err=True,
            )
            return LoopResult(
                session_id=session_id,
                verdict="terminate",
                iterations=iteration + 1,
                history=history,
                result_text=doer_result,
            )

        # verdict == "retry" — spawn next doer iteration with feedback
        if iteration + 1 >= max_iterations:
            click.echo(
                f"Loop: max iterations ({max_iterations}) reached without acceptance.",
                err=True,
            )
            return LoopResult(
                session_id=session_id,
                verdict="max_iterations",
                iterations=iteration + 1,
                history=history,
                result_text=doer_result,
            )

        # Build retry prompt with summary + checker feedback
        retry_prompt = (
            f"{prompt}\n\n"
            f"# Previous Attempt Summary (iteration {iteration})\n\n"
            f"{doer_summary}\n\n"
            f"# Checker Feedback\n\n"
            f"The checker reviewed your previous output and requested a retry:\n\n"
            f"{feedback}\n\n"
            f"Please address this feedback and try again."
        )

        # Spawn next doer iteration (summary replaces full result pipe)
        current_doer_id = spawn_session(
            prompt=retry_prompt,
            dangerously_skip_permissions=dangerously_skip_permissions,
            parent_session_id=session_id,
        )

    # Should not normally reach here, but safety net
    return LoopResult(
        session_id=session_id,
        verdict="max_iterations",
        iterations=max_iterations,
        history=history,
        result_text="",
    )


def spawn_and_run(
    session_id: str,
    prompt: str,
    checker: str,
    max_iterations: int = 3,
    checker_model: str = "",
    model: str = "",
    dangerously_skip_permissions: bool = False,
) -> LoopResult:
    """Combine session creation + contract sending + loop execution.

    This is the high-level entry point for running a complete doer→checker
    loop. It assumes the session and tmux window are already created and
    the contract has been sent. It runs the loop and returns the result.

    For the full spawn flow (tmux window creation, contract sending, etc.),
    use the spawn CLI command. This function focuses on the loop execution.

    Returns:
        LoopResult with the final verdict and history.
    """
    return run_loop(
        session_id=session_id,
        prompt=prompt,
        checker=checker,
        max_iterations=max_iterations,
        checker_model=checker_model or model,
        dangerously_skip_permissions=dangerously_skip_permissions,
    )
