"""Spawn command for scope.

Creates a new scope session with Claude Code running in a tmux window.
Every spawn is a loop: doer → checker → (retry or accept), up to --max-iterations.
"""

import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import click
from watchfiles import watch

from scope.core.contract import generate_checker_contract, generate_contract
from scope.core.dag import detect_cycle
from scope.core.session import Session
from scope.core.state import (
    ensure_scope_dir,
    load_session,
    load_session_by_alias,
    next_id,
    resolve_id,
    save_loop_state,
    save_session,
)
from scope.core.tmux import (
    TmuxError,
    create_window,
    get_scope_session,
    in_tmux,
    pane_target_for_window,
    send_keys,
    set_pane_option,
    tmux_window_name,
)
from scope.hooks.install import install_tmux_hooks

# Placeholder task - will be inferred from first prompt via hooks
PENDING_TASK = "(pending...)"
CONTRACT_CHUNK_SIZE = 2000
TERMINAL_STATES = {"done", "aborted", "failed", "exited"}


def _wait_for_sessions(session_ids: list[str]) -> None:
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


def _collect_piped_results(session_ids: list[str]) -> list[str]:
    """Collect result text from completed sessions.

    Each result is prefixed with attribution so the child session
    knows where the content came from.

    Returns:
        List of formatted result strings, one per session with a result file.
    """
    scope_dir = ensure_scope_dir()
    results: list[str] = []
    for sid in session_ids:
        result_file = scope_dir / "sessions" / sid / "result"
        if result_file.exists():
            text = result_file.read_text().strip()
            if text:
                session = load_session(sid)
                label = sid
                if session and session.alias:
                    label = f"{session.alias} ({sid})"
                results.append(f"The previous session [{label}] produced:\n\n{text}")
    return results


def _task_still_pending(task_path: Path) -> bool:
    """Return True if the task file still contains the pending placeholder."""
    try:
        return task_path.read_text().strip() == PENDING_TASK
    except FileNotFoundError:
        return False


def _wait_for_task_update(task_path: Path, timeout: float) -> bool:
    """Wait for task to move past pending; return True if updated."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _task_still_pending(task_path):
            return True
        time.sleep(0.1)
    return not _task_still_pending(task_path)


def _send_contract(target: str, contract: str) -> None:
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


@click.command()
@click.argument("prompt")
@click.option(
    "--id",
    "alias",
    default="",
    help="Human-readable alias for the session (must be unique)",
)
@click.option(
    "--after",
    "after",
    default="",
    help="Comma-separated list of session IDs or aliases this session depends on",
)
@click.option(
    "--pipe",
    "pipe",
    default="",
    help="Comma-separated session IDs/aliases to pipe results from (implies --after)",
)
@click.option(
    "--plan",
    is_flag=True,
    help="Start Claude in plan mode",
)
@click.option(
    "--model",
    default="",
    help="Model to use (e.g., sonnet, opus, haiku)",
)
@click.option(
    "--dangerously-skip-permissions",
    is_flag=True,
    envvar="SCOPE_DANGEROUSLY_SKIP_PERMISSIONS",
    help="Pass --dangerously-skip-permissions to spawned Claude instance",
)
@click.option(
    "--checker",
    "checker",
    required=True,
    help="REQUIRED. Command or agent prompt to verify doer output. "
    'Prefix with "agent:" for an agent checker (runs as a tmux session). '
    'Shell command: exit 0 = pass. Example: --checker "pytest tests/" or '
    '--checker "agent: Review for edge cases. Verdict: ACCEPT/RETRY/TERMINATE"',
)
@click.option(
    "--max-iterations",
    "max_iterations",
    type=int,
    default=3,
    show_default=True,
    help="Maximum loop iterations before terminating.",
)
@click.option(
    "--checker-model",
    "checker_model",
    default="",
    help="Model for agent checker (default: same as doer).",
)
@click.pass_context
def spawn(
    ctx: click.Context,
    prompt: str,
    alias: str,
    after: str,
    pipe: str,
    plan: bool,
    model: str,
    dangerously_skip_permissions: bool,
    checker: str,
    max_iterations: int,
    checker_model: str,
) -> None:
    """Spawn a new scope session.

    Every spawn is a loop: doer → checker → (retry or accept).
    The --checker flag is required — every task must declare its verification.

    Creates a tmux window running Claude Code with the given prompt.
    Prints the session ID to stdout.

    PROMPT is the initial prompt/context to send to Claude Code.
    The task description will be inferred automatically from the prompt.

    Examples:

        scope spawn "Write tests for auth" --checker "pytest tests/"

        scope spawn "Implement feature" --checker "agent: Review for correctness"

        scope spawn "Fix bug" --checker "python verify.py" --max-iterations 5
    """
    # Check if flag was passed via parent context
    if ctx.obj and ctx.obj.get("dangerously_skip_permissions"):
        dangerously_skip_permissions = True

    # Validate alias uniqueness if provided
    if alias:
        existing = load_session_by_alias(alias)
        if existing is not None:
            click.echo(
                f"Error: alias '{alias}' is already used by session {existing.id}\n"
                f"  Cause: Session aliases must be unique across all sessions.\n"
                f"  Fix: Choose a different alias:\n"
                f'    scope spawn --id {alias}-2 "your prompt here"',
                err=True,
            )
            raise SystemExit(1)

    # Parse and resolve dependencies
    depends_on: list[str] = []
    if after:
        for dep_ref in after.split(","):
            dep_ref = dep_ref.strip()
            if not dep_ref:
                continue
            resolved = resolve_id(dep_ref)
            if resolved is None:
                click.echo(
                    f"Error: dependency '{dep_ref}' not found\n"
                    f"  Cause: '{dep_ref}' is not a valid session ID or alias.\n"
                    f"  Fix: List available sessions and use a valid ID or alias:\n"
                    f"    scope list\n"
                    f'    scope spawn --after <session-id> "your prompt here"',
                    err=True,
                )
                raise SystemExit(1)
            depends_on.append(resolved)

    # Parse and resolve piped sessions (--pipe implies --after)
    pipe_ids: list[str] = []
    if pipe:
        for dep_ref in pipe.split(","):
            dep_ref = dep_ref.strip()
            if not dep_ref:
                continue
            resolved = resolve_id(dep_ref)
            if resolved is None:
                click.echo(
                    f"Error: piped session '{dep_ref}' not found\n"
                    f"  Cause: '{dep_ref}' is not a valid session ID or alias.\n"
                    f"  Fix: List available sessions and use a valid ID or alias:\n"
                    f"    scope list\n"
                    f'    scope spawn --pipe <session-id> "your prompt here"',
                    err=True,
                )
                raise SystemExit(1)
            pipe_ids.append(resolved)
            # --pipe implies --after: add to depends_on if not already present
            if resolved not in depends_on:
                depends_on.append(resolved)

    # Wait for piped sessions to complete and collect their results
    prior_results: list[str] | None = None
    if pipe_ids:
        _wait_for_sessions(pipe_ids)
        prior_results = _collect_piped_results(pipe_ids) or None

    # Get parent from environment (for nested sessions)
    parent = os.environ.get("SCOPE_SESSION_ID", "")

    # Get next available ID
    session_id = next_id(parent)

    # Check for cycles before creating the session
    if depends_on and detect_cycle(session_id, depends_on):
        dep_list = ", ".join(depends_on)
        click.echo(
            f"Error: adding dependencies [{dep_list}] would create a circular dependency\n"
            f"  Cause: One of these sessions (or their dependencies) already depends on\n"
            f"  work that would be produced by this new session.\n"
            f"  Fix: Remove the conflicting dependency from --after, or spawn this\n"
            f"  session without dependencies and coordinate manually:\n"
            f"    scope list                              # View the dependency graph\n"
            f'    scope spawn "your prompt here"         # Spawn without --after',
            err=True,
        )
        raise SystemExit(1)

    # Create session object - task will be inferred by hooks
    window_name = tmux_window_name(session_id)
    session = Session(
        id=session_id,
        task=PENDING_TASK,
        parent=parent,
        state="running",
        tmux_session=window_name,  # Store window name (kept as tmux_session for compat)
        created_at=datetime.now(timezone.utc),
        alias=alias,
        depends_on=depends_on,
    )

    # Create tmux window with Claude Code BEFORE saving session
    # This prevents a race where load_all() sees a "running" session
    # with a tmux_session set but the window doesn't exist yet,
    # causing it to be incorrectly marked as "aborted"
    try:
        # Allow overriding command for tests (e.g., "sleep infinity" when claude isn't installed)
        command = os.environ.get("SCOPE_SPAWN_COMMAND", "claude")
        if command == "claude":
            if plan:
                command += " --permission-mode plan"
            if model:
                command += f" --model {shlex.quote(model)}"
            if dangerously_skip_permissions:
                command += " --dangerously-skip-permissions"

        # Build environment for spawned session
        env = {"SCOPE_SESSION_ID": session_id}
        if dangerously_skip_permissions:
            env["SCOPE_DANGEROUSLY_SKIP_PERMISSIONS"] = "1"
        if path := os.environ.get("PATH"):
            env["PATH"] = path
        for key, value in os.environ.items():
            if key.startswith(("CLAUDE", "ANTHROPIC")):
                env[key] = value

        create_window(
            name=window_name,
            command=command,
            cwd=Path.cwd(),  # Project root
            env=env,
        )

        try:
            set_pane_option(
                pane_target_for_window(window_name),
                "@scope_session_id",
                session_id,
            )
        except TmuxError:
            pass

        # Ensure tmux hook is installed AFTER create_window (so server exists)
        # Idempotent - safe to call on every spawn
        install_tmux_hooks()

        # Now that window exists, save session to filesystem
        save_session(session)

        # Check LRU cache and evict oldest completed sessions if over limit
        from scope.core.lru import check_and_evict

        check_and_evict()

        # Generate and save contract
        scope_dir = ensure_scope_dir()
        session_dir = scope_dir / "sessions" / session_id

        contract = generate_contract(
            prompt=prompt,
            depends_on=depends_on if depends_on else None,
            prior_results=prior_results,
        )
        (session_dir / "contract.md").write_text(contract)

        # Initialize loop state
        save_loop_state(
            session_id=session_id,
            checker=checker,
            max_iterations=max_iterations,
            current_iteration=0,
            history=[],
        )

        # Wait for Claude Code to signal readiness via SessionStart hook
        # Skip if SCOPE_SKIP_READY_CHECK is set (used in tests)
        skip_ready_check = os.environ.get("SCOPE_SKIP_READY_CHECK", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if not skip_ready_check:
            ready_file = session_dir / "ready"
            timeout = 10  # seconds
            start_time = time.time()
            while not ready_file.exists():
                if time.time() - start_time > timeout:
                    click.echo(
                        f"Warning: Claude Code did not signal ready within {timeout}s\n"
                        f"  Sending prompt anyway, but the session may not receive it correctly.\n"
                        f"  Possible causes and fixes:\n"
                        f"    - Claude Code slow to start → Wait and retry\n"
                        f"    - SessionStart hook not installed → Run: scope setup\n"
                        f"    - Claude Code crashed → Check window: tmux select-window -t {get_scope_session()}:{window_name}",
                        err=True,
                    )
                    break
                time.sleep(0.1)
            # SessionStart fires during startup but the input prompt may not be ready yet
            time.sleep(0.3)
        else:
            # In test environment, wait a short time for process to start
            time.sleep(0.5)

        # Use full session:window target when not inside tmux
        if in_tmux():
            target = f":{window_name}"
        else:
            target = f"{get_scope_session()}:{window_name}"

        # IMPORTANT: invoke /scope as its OWN message so Claude Code executes it
        # as a command (instead of treating it as plain text inside a larger prompt).
        try:
            send_keys(target, "/scope", submit=True, verify=False)
            time.sleep(0.3)
        except TmuxError:
            pass

        _send_contract(target, contract)

        # If the task is still pending, Enter may not have been delivered.
        # Resend Enter up to 5 times to ensure the prompt submits.
        if not skip_ready_check:
            task_path = session_dir / "task"
            if _task_still_pending(task_path):
                for _ in range(5):
                    if _wait_for_task_update(task_path, timeout=1.0):
                        break
                    try:
                        send_keys(target, "", submit=True, verify=False)
                    except TmuxError:
                        pass
                _wait_for_task_update(task_path, timeout=1.0)

    except TmuxError as e:
        error_msg = str(e)
        click.echo(f"Error: tmux operation failed: {error_msg}", err=True)

        # Provide actionable guidance based on the error
        if "Failed to create" in error_msg:
            if "session" in error_msg.lower():
                click.echo(
                    "  Cause: The tmux server is not running or is inaccessible.\n"
                    "  Fix: Start tmux and verify it works:\n"
                    "    tmux new-session -d -s test && tmux kill-session -t test",
                    err=True,
                )
            else:
                click.echo(
                    "  Cause: Could not create a tmux window for this session.\n"
                    "  Fix: Verify tmux is running:\n"
                    "    tmux list-sessions",
                    err=True,
                )
        elif "send" in error_msg.lower():
            click.echo(
                "  Cause: The tmux window may have closed unexpectedly.\n"
                "  Fix: Check if Claude Code is installed and working:\n"
                "    claude --version",
                err=True,
            )
        else:
            click.echo(
                "  Cause: tmux may not be installed or is not running.\n"
                "  Fix: Install tmux:\n"
                "    brew install tmux   # macOS\n"
                "    apt install tmux    # Linux",
                err=True,
            )
        raise SystemExit(1)

    # Output session ID (printed before loop starts so callers can track it)
    click.echo(session_id)

    # --- Loop execution: doer → checker → (retry or accept) ---
    # Skip loop in test environments or when explicitly disabled
    skip_loop = os.environ.get("SCOPE_SKIP_LOOP", "").lower() in ("1", "true", "yes")
    if not skip_loop:
        _run_loop(
            session_id=session_id,
            prompt=prompt,
            checker=checker,
            max_iterations=max_iterations,
            checker_model=checker_model or model,
            dangerously_skip_permissions=dangerously_skip_permissions,
        )


# ---------------------------------------------------------------------------
# Loop engine
# ---------------------------------------------------------------------------


def _run_loop(
    session_id: str,
    prompt: str,
    checker: str,
    max_iterations: int,
    checker_model: str,
    dangerously_skip_permissions: bool,
) -> None:
    """Execute the doer→checker loop.

    Waits for the doer to complete, runs the checker, and either accepts
    or retries with feedback up to max_iterations times.
    """
    scope_dir = ensure_scope_dir()
    history: list[dict] = []
    current_doer_id = session_id

    for iteration in range(max_iterations):
        # Wait for current doer to complete
        _wait_for_sessions([current_doer_id])

        # Read doer result and produce a summary for downstream consumers
        doer_result = _read_result(scope_dir, current_doer_id)

        # Check if doer failed/aborted — no point running checker
        session = load_session(current_doer_id)
        if session and session.state in {"aborted", "failed", "exited"}:
            click.echo(
                f"Loop: doer session {current_doer_id} ended with state '{session.state}' "
                f"at iteration {iteration}. Terminating loop.",
                err=True,
            )
            break

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
        verdict, feedback = _run_checker(
            checker=checker,
            doer_result=doer_summary,
            iteration=iteration,
            history=history,
            checker_model=checker_model,
            dangerously_skip_permissions=dangerously_skip_permissions,
        )

        # Record history
        history.append(
            {
                "iteration": iteration,
                "doer_session": current_doer_id,
                "verdict": verdict,
                "feedback": feedback,
            }
        )

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
            return

        if verdict == "terminate":
            click.echo(
                f"Loop: checker terminated at iteration {iteration}. "
                f"Feedback: {feedback}",
                err=True,
            )
            return

        # verdict == "retry" — spawn next doer iteration with feedback
        if iteration + 1 >= max_iterations:
            click.echo(
                f"Loop: max iterations ({max_iterations}) reached without acceptance.",
                err=True,
            )
            return

        # Build retry prompt with summary + checker feedback
        # (reuse doer_summary computed above for the checker)
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
        current_doer_id = _spawn_session(
            prompt=retry_prompt,
            dangerously_skip_permissions=dangerously_skip_permissions,
            parent_session_id=session_id,
        )


def _read_result(scope_dir: Path, session_id: str) -> str:
    """Read the result file for a completed session."""
    result_file = scope_dir / "sessions" / session_id / "result"
    if result_file.exists():
        return result_file.read_text().strip()
    return ""


def _run_checker(
    checker: str,
    doer_result: str,
    iteration: int,
    history: list[dict],
    checker_model: str,
    dangerously_skip_permissions: bool,
) -> tuple[str, str]:
    """Run the checker and return (verdict, feedback).

    Command checker: runs as subprocess, exit 0 = accept, non-zero = retry.
    Agent checker (prefix "agent:"): spawns a tmux session to evaluate.

    Returns:
        Tuple of (verdict, feedback) where verdict is "accept", "retry", or "terminate".
    """
    if checker.startswith("agent:"):
        return _run_agent_checker(
            checker_prompt=checker[len("agent:") :].strip(),
            doer_result=doer_result,
            iteration=iteration,
            history=history,
            checker_model=checker_model,
            dangerously_skip_permissions=dangerously_skip_permissions,
        )
    else:
        return _run_command_checker(command=checker)


def _run_command_checker(command: str) -> tuple[str, str]:
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


def _run_agent_checker(
    checker_prompt: str,
    doer_result: str,
    iteration: int,
    history: list[dict],
    checker_model: str,
    dangerously_skip_permissions: bool,
) -> tuple[str, str]:
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

    checker_id = _spawn_session(
        prompt=contract,
        model=checker_model,
        dangerously_skip_permissions=dangerously_skip_permissions,
    )

    # Wait for checker session to finish
    _wait_for_sessions([checker_id])

    # Read checker result
    scope_dir = ensure_scope_dir()
    session = load_session(checker_id)
    if session and session.state in {"aborted", "failed", "exited"}:
        return (
            "retry",
            f"Checker session {checker_id} ended with state '{session.state}'",
        )

    response = _read_result(scope_dir, checker_id)
    if not response:
        return ("retry", f"Checker session {checker_id} produced no output")

    return _parse_verdict(response)


def _parse_verdict(response: str) -> tuple[str, str]:
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


def _spawn_session(
    prompt: str,
    model: str = "",
    dangerously_skip_permissions: bool = False,
    pipe_from: str = "",
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
    if pipe_from:
        cmd.extend(["--pipe", pipe_from])

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
