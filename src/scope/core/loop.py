"""Loop engine for scope.

Extracted from spawn.py — the doer→checker loop as a reusable module.
Rubric-driven verification: all checkers are internally rubrics.
"""

import hashlib
import os
import re
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
class Rubric:
    """Parsed rubric with optional sections."""

    title: str = ""
    gates: list[str] = field(default_factory=list)
    criteria: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def has_gates(self) -> bool:
        return bool(self.gates)

    @property
    def has_criteria(self) -> bool:
        return bool(self.criteria) or bool(self.nice_to_have)


def parse_rubric(text: str) -> Rubric:
    """Parse a rubric markdown file into structured sections.

    Supports these sections:
    - ## Gates — shell commands (extracted from backtick-wrapped list items)
    - ## Criteria — must-have natural language criteria
    - ## Nice to Have — advisory criteria
    - ## Notes — background context (free-form text)

    Args:
        text: Rubric markdown content.

    Returns:
        Parsed Rubric dataclass.
    """
    rubric = Rubric()

    # Extract title from # heading (not ##)
    title_match = re.match(r"^#\s+(.+)$", text.strip(), re.MULTILINE)
    if title_match:
        rubric.title = title_match.group(1).strip()

    # Split into sections by ## headings
    section_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    sections: list[tuple[str, str]] = []
    matches = list(section_pattern.finditer(text))

    for i, match in enumerate(matches):
        heading = match.group(1).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((heading, body))

    for heading, body in sections:
        if heading == "gates":
            # Extract commands from backtick-wrapped list items: - `command`
            for line in body.split("\n"):
                line = line.strip()
                m = re.match(r"^-\s+`(.+?)`", line)
                if m:
                    rubric.gates.append(m.group(1))
        elif heading == "criteria":
            for line in body.split("\n"):
                line = line.strip()
                m = re.match(r"^-\s+(.+)$", line)
                if m:
                    rubric.criteria.append(m.group(1))
        elif heading in ("nice to have", "nice-to-have"):
            for line in body.split("\n"):
                line = line.strip()
                m = re.match(r"^-\s+(.+)$", line)
                if m:
                    rubric.nice_to_have.append(m.group(1))
        elif heading == "notes":
            rubric.notes = body

    return rubric


def detect_checker_type(checker: str) -> str:
    """Detect the type of checker specification.

    Returns:
        "file" — path to a rubric file
        "agent" — agent: prefixed prompt
        "command" — shell command
    """
    if checker.startswith("agent:"):
        return "agent"
    # Check if it looks like a file path (exists or has .md extension)
    if Path(checker).suffix in (".md", ".markdown"):
        return "file"
    if Path(checker).is_file():
        return "file"
    return "command"


def sugar_to_rubric(checker: str) -> str:
    """Convert checker sugar to rubric markdown.

    Args:
        checker: A shell command or "agent: ..." string.

    Returns:
        Rubric markdown content.
    """
    checker_type = detect_checker_type(checker)

    if checker_type == "agent":
        prompt = checker[len("agent:"):].strip()
        return f"## Criteria\n- {prompt}\n"
    elif checker_type == "command":
        return f"## Gates\n- `{checker}`\n"
    else:
        # File path — should be read directly, not converted
        raise ValueError(f"Cannot convert file path to rubric: {checker}")


def rubric_hash(content: str) -> str:
    """Compute a short hash of rubric content for change tracking."""
    return hashlib.sha256(content.encode()).hexdigest()[:8]


def load_rubric(rubric_path: str) -> tuple[Rubric, str, str]:
    """Load and parse a rubric file.

    Returns:
        Tuple of (parsed Rubric, raw content, content hash).
    """
    content = Path(rubric_path).read_text()
    parsed = parse_rubric(content)
    return (parsed, content, rubric_hash(content))


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


def iter_session_id(loop_id: str, iteration: int, role: str) -> str:
    """Build an iteration-indexed session ID for a loop child.

    Examples:
        >>> iter_session_id("2.1", 0, "check")
        '2.1-0-check'
        >>> iter_session_id("2.1", 1, "do")
        '2.1-1-do'
    """
    return f"{loop_id}-{iteration}-{role}"


def spawn_session(
    prompt: str,
    model: str = "",
    dangerously_skip_permissions: bool = False,
    parent_session_id: str = "",
    session_id: str = "",
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
    if session_id:
        cmd.extend(["--session-id", session_id])
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

    checker_id_str = iter_session_id(parent_session_id, iteration, "check") if parent_session_id else ""
    checker_id = spawn_session(
        prompt=contract,
        model=checker_model,
        dangerously_skip_permissions=dangerously_skip_permissions,
        parent_session_id=parent_session_id,
        session_id=checker_id_str,
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


def run_gates(gates: list[str]) -> list[dict]:
    """Run all gate commands and return structured results.

    Each gate is run as a subprocess. Results include command, verdict, and output.

    Args:
        gates: List of shell commands to run.

    Returns:
        List of dicts with keys: command, verdict ("pass"/"fail"/"error"), output.
    """
    results = []
    for command in gates:
        verdict, output = run_command_checker(command=command)
        # Normalize: run_command_checker returns "accept"/"retry"/"terminate"
        gate_verdict = "pass" if verdict == "accept" else "fail"
        results.append({
            "command": command,
            "verdict": gate_verdict,
            "output": output,
        })
    return results


def run_rubric_checker(
    rubric: Rubric,
    doer_result: str,
    iteration: int,
    history: list[dict],
    checker_model: str,
    dangerously_skip_permissions: bool,
    parent_session_id: str = "",
) -> tuple[str, str, str, list[dict], str]:
    """Run composite rubric-based verification.

    1. Run all gates (shell commands)
    2. If criteria exist, run agent checker with gate results as context
    3. Compute composite verdict

    Returns:
        Tuple of (verdict, feedback, checker_session_id, gate_results, criteria_summary).
    """
    gate_results: list[dict] = []
    criteria_summary = ""
    checker_session_id = ""

    # Step 1: Run gates
    if rubric.has_gates:
        gate_results = run_gates(rubric.gates)

    # Step 2: Run agent checker if criteria exist
    if rubric.has_criteria:
        contract = generate_checker_contract(
            checker_prompt="",  # Not used in rubric mode
            doer_result=doer_result,
            iteration=iteration,
            history=history if history else None,
            gate_results=gate_results if gate_results else None,
            criteria=rubric.criteria if rubric.criteria else None,
            nice_to_have=rubric.nice_to_have if rubric.nice_to_have else None,
            notes=rubric.notes,
        )

        checker_id_str = iter_session_id(parent_session_id, iteration, "check") if parent_session_id else ""
        checker_session_id = spawn_session(
            prompt=contract,
            model=checker_model,
            dangerously_skip_permissions=dangerously_skip_permissions,
            parent_session_id=parent_session_id,
            session_id=checker_id_str,
        )

        wait_for_sessions([checker_session_id])

        scope_dir = ensure_scope_dir()
        session = load_session(checker_session_id)
        if session and session.state in {"aborted", "failed", "exited"}:
            return (
                "retry",
                f"Checker session {checker_session_id} ended with state '{session.state}'",
                checker_session_id,
                gate_results,
                "",
            )

        response = read_result(scope_dir, checker_session_id)
        if not response:
            return (
                "retry",
                f"Checker session {checker_session_id} produced no output",
                checker_session_id,
                gate_results,
                "",
            )

        # Parse per-criterion results from agent response
        criteria_summary = _parse_criteria_summary(
            response, len(rubric.criteria), len(rubric.nice_to_have)
        )

        # Step 3: Composite verdict
        gates_pass = all(g["verdict"] == "pass" for g in gate_results)
        agent_verdict, agent_feedback = parse_verdict(response)

        if agent_verdict == "terminate":
            return ("terminate", agent_feedback, checker_session_id, gate_results, criteria_summary)

        if not gates_pass:
            # Build feedback from failed gates + agent feedback
            failed_gates = [g for g in gate_results if g["verdict"] != "pass"]
            gate_feedback = "Failed gates:\n" + "\n".join(
                f"- `{g['command']}`: {g['output'][:500]}" for g in failed_gates
            )
            combined = f"{gate_feedback}\n\nAgent feedback:\n{agent_feedback}"
            return ("retry", combined, checker_session_id, gate_results, criteria_summary)

        if agent_verdict == "accept":
            return ("accept", agent_feedback, checker_session_id, gate_results, criteria_summary)
        else:
            return ("retry", agent_feedback, checker_session_id, gate_results, criteria_summary)

    else:
        # Gates-only rubric: no agent checker needed
        if not gate_results:
            # Empty rubric — accept by default
            return ("accept", "Empty rubric — no checks to run", "", [], "")

        gates_pass = all(g["verdict"] == "pass" for g in gate_results)
        if gates_pass:
            gate_summary = "\n".join(
                f"- `{g['command']}`: PASS" for g in gate_results
            )
            return ("accept", gate_summary, "", gate_results, "")
        else:
            failed_gates = [g for g in gate_results if g["verdict"] != "pass"]
            gate_feedback = "\n".join(
                f"- `{g['command']}`: FAIL\n{g['output'][:500]}" for g in failed_gates
            )
            return ("retry", gate_feedback, "", gate_results, "")


def _parse_criteria_summary(
    response: str, num_criteria: int, num_nice: int
) -> str:
    """Parse per-criterion PASS/FAIL counts from agent response.

    Best-effort parsing. Falls back to empty string if parsing fails.

    Returns:
        Summary string like "2/3 must  1/2 nice" or "".
    """
    # Count PASS/FAIL mentions in the response
    lines = response.split("\n")
    must_pass = 0
    nice_pass = 0

    # Simple heuristic: look for numbered items with PASS/FAIL
    in_must = False
    in_nice = False
    must_count = 0
    nice_count = 0

    for line in lines:
        line_upper = line.upper().strip()
        if "MUST-HAVE" in line_upper or "MUST HAVE" in line_upper:
            in_must = True
            in_nice = False
            continue
        if "NICE-TO-HAVE" in line_upper or "NICE TO HAVE" in line_upper:
            in_nice = True
            in_must = False
            continue
        if line_upper.startswith("#"):
            in_must = False
            in_nice = False
            continue

        # Check for numbered items with PASS/FAIL
        if re.match(r"^\d+\.", line.strip()):
            if in_must:
                must_count += 1
                if "PASS" in line_upper:
                    must_pass += 1
            elif in_nice:
                nice_count += 1
                if "PASS" in line_upper:
                    nice_pass += 1

    # Use parsed counts, fall back to provided counts
    total_must = must_count if must_count > 0 else num_criteria
    total_nice = nice_count if nice_count > 0 else num_nice

    parts = []
    if total_must > 0:
        parts.append(f"{must_pass}/{total_must} must")
    if total_nice > 0:
        parts.append(f"{nice_pass}/{total_nice} nice")

    return "  ".join(parts)


def run_checker(
    checker: str,
    doer_result: str,
    iteration: int,
    history: list[dict],
    checker_model: str,
    dangerously_skip_permissions: bool,
    parent_session_id: str = "",
    rubric_path: str = "",
) -> tuple[str, str, str, list[dict], str]:
    """Run the checker and return (verdict, feedback, checker_session_id, gate_results, criteria_summary).

    When rubric_path is set, loads and uses rubric-driven verification.
    Otherwise falls back to legacy command/agent checker.

    Returns:
        Tuple of (verdict, feedback, checker_session_id, gate_results, criteria_summary).
        gate_results and criteria_summary are empty for legacy checkers.
    """
    if rubric_path:
        rubric, _content, _hash = load_rubric(rubric_path)
        return run_rubric_checker(
            rubric=rubric,
            doer_result=doer_result,
            iteration=iteration,
            history=history,
            checker_model=checker_model,
            dangerously_skip_permissions=dangerously_skip_permissions,
            parent_session_id=parent_session_id,
        )

    # Legacy path
    if checker.startswith("agent:"):
        verdict, feedback, cid = run_agent_checker(
            checker_prompt=checker[len("agent:") :].strip(),
            doer_result=doer_result,
            iteration=iteration,
            history=history,
            checker_model=checker_model,
            dangerously_skip_permissions=dangerously_skip_permissions,
            parent_session_id=parent_session_id,
        )
        return (verdict, feedback, cid, [], "")
    else:
        verdict, feedback = run_command_checker(command=checker)
        return (verdict, feedback, "", [], "")


def run_loop(
    session_id: str,
    prompt: str,
    checker: str,
    max_iterations: int,
    checker_model: str,
    dangerously_skip_permissions: bool,
    rubric_path: str = "",
) -> LoopResult:
    """Execute the doer->checker loop.

    Waits for the doer to complete, runs the checker, and either accepts
    or retries with feedback up to max_iterations times.

    When rubric_path is set, the rubric file is re-read each iteration
    (hot-reload for mid-loop editing).

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

        # Compute rubric hash for this iteration (hot-reload: re-read each time)
        iter_rubric_hash = ""
        if rubric_path and Path(rubric_path).exists():
            _rubric, _content, iter_rubric_hash = load_rubric(rubric_path)

        # Run checker with summarized result
        verdict, feedback, checker_session_id, gate_results, criteria_summary = run_checker(
            checker=checker,
            doer_result=doer_summary,
            iteration=iteration,
            history=history,
            checker_model=checker_model,
            dangerously_skip_permissions=dangerously_skip_permissions,
            parent_session_id=session_id,
            rubric_path=rubric_path,
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
        if gate_results:
            entry["gates"] = gate_results
        if criteria_summary:
            entry["criteria_summary"] = criteria_summary
        if iter_rubric_hash:
            entry["rubric_hash"] = iter_rubric_hash
        history.append(entry)

        # Persist loop state
        save_loop_state(
            session_id=session_id,
            checker=checker,
            max_iterations=max_iterations,
            current_iteration=iteration,
            history=history,
            rubric_path=rubric_path,
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
        new_id = iter_session_id(session_id, iteration + 1, "do")
        current_doer_id = spawn_session(
            prompt=retry_prompt,
            dangerously_skip_permissions=dangerously_skip_permissions,
            parent_session_id=session_id,
            session_id=new_id,
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
    rubric_path: str = "",
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
        rubric_path=rubric_path,
    )
