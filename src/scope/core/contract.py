"""Contract generation for scope sessions.

Generates markdown contracts that are sent to Claude Code as the initial prompt.
"""


def generate_contract(
    prompt: str,
    depends_on: list[str] | None = None,
    *,
    phase: str | None = None,
    parent_intent: str | None = None,
    prior_results: list[str] | None = None,
    file_scope: list[str] | None = None,
    verify: list[str] | None = None,
) -> str:
    """Generate a contract markdown for a session.

    The contract is sent to Claude Code as the initial prompt via tmux send-keys.

    Args:
        prompt: The initial prompt/context to send to Claude Code.
        depends_on: Optional list of session IDs this session depends on.
            If provided, the contract will include instructions to wait for
            these dependencies before starting work.
        phase: Optional phase metadata, e.g. 'RED' for TDD red phase.
        parent_intent: Optional parent/orchestrator goal context.
        prior_results: Optional list of results from prior/piped sessions.
        file_scope: Optional list of file/directory constraints.
        verify: Optional list of verification criteria (natural language or commands).

    Returns:
        Markdown string containing the contract.
    """
    sections = []

    # NOTE: /scope is invoked separately by the spawner (Scope TUI / CLI)
    # to ensure the command is executed as a command, not embedded in a larger prompt.

    # Add dependencies section if there are dependencies
    if depends_on:
        deps_str = " ".join(depends_on)
        sections.append(
            f"# Dependencies\n\n"
            f"Before starting, wait for your dependencies to complete:\n"
            f"```bash\nscope wait {deps_str}\n```\n\n"
            f"Use the results from these sessions to inform your work."
        )

    # Add phase metadata
    if phase:
        sections.append(f"# Phase\n\nYou are in the **{phase}** phase.")

    # Add parent intent
    if parent_intent:
        sections.append(f"# Parent Intent\n\n{parent_intent}")

    # Add prior results
    if prior_results:
        results_body = "\n\n---\n\n".join(prior_results)
        sections.append(f"# Prior Results\n\n{results_body}")

    # Add task section
    sections.append(f"# Task\n{prompt}")

    # Add file scope constraints
    if file_scope:
        constraints = "\n".join(f"- `{path}`" for path in file_scope)
        sections.append(
            f"# File Scope\n\n"
            f"Only modify files within the following paths:\n{constraints}"
        )

    # Add verification section
    if verify:
        checks = "\n".join(f"- {criterion}" for criterion in verify)
        sections.append(
            f"# Verification\n\n"
            f"Your output will be verified against these criteria:\n{checks}"
        )

    return "\n\n".join(sections)


def generate_checker_contract(
    checker_prompt: str,
    doer_result: str,
    iteration: int,
    history: list[dict] | None = None,
    *,
    gate_results: list[dict] | None = None,
    criteria: list[str] | None = None,
    nice_to_have: list[str] | None = None,
    notes: str = "",
) -> str:
    """Generate a checker contract for verifying doer output.

    The checker sees the doer's result (not its reasoning/trajectory),
    iteration history, and is asked to render a verdict.

    When rubric sections are provided (criteria, nice_to_have, notes, gate_results),
    the contract uses the rubric-aware format with per-criterion evaluation.
    Otherwise falls back to the simple checker_prompt format.

    Args:
        checker_prompt: The checker's verification prompt (used when no rubric criteria).
        doer_result: The doer's final output text.
        iteration: Current iteration number (0-indexed).
        history: Prior iteration records with keys: iteration, verdict, feedback.
        gate_results: List of dicts with keys: command, verdict, output.
        criteria: List of must-have criterion strings from rubric.
        nice_to_have: List of nice-to-have criterion strings from rubric.
        notes: Background context from rubric ## Notes section.

    Returns:
        Markdown string containing the checker contract.
    """
    sections = []

    # Use rubric-aware format when criteria are provided
    if criteria or nice_to_have:
        return _generate_rubric_checker_contract(
            doer_result=doer_result,
            iteration=iteration,
            history=history,
            gate_results=gate_results,
            criteria=criteria or [],
            nice_to_have=nice_to_have or [],
            notes=notes,
        )

    # Legacy format: simple checker prompt
    sections.append(
        "# Role\n\n"
        "You are a **checker**. Your job is to verify the doer's output and render a verdict.\n\n"
        "You MUST end your response with exactly one of these verdicts on its own line:\n"
        "- `ACCEPT` — the output meets the criteria\n"
        "- `RETRY` — the output needs improvement (provide specific feedback)\n"
        "- `TERMINATE` — the task is fundamentally broken and retrying won't help"
    )

    # Checker criteria
    sections.append(f"# Checker Criteria\n\n{checker_prompt}")

    # Doer output
    sections.append(f"# Doer Output\n\n{doer_result}")

    # Iteration context
    sections.append(f"# Iteration\n\nThis is iteration {iteration}.")

    # History of prior iterations
    if history:
        sections.append(_format_history(history))

    return "\n\n".join(sections)


def _format_history(history: list[dict]) -> str:
    """Format iteration history as a markdown section."""
    history_lines = []
    for entry in history:
        verdict = entry.get("verdict", "unknown").upper()
        feedback = entry.get("feedback", "")
        line = f"- Iteration {entry.get('iteration', '?')}: **{verdict}**"
        if feedback:
            # Truncate long feedback in history summaries
            summary = feedback[:200] + "..." if len(feedback) > 200 else feedback
            line += f" — {summary}"
        history_lines.append(line)
    history_body = "\n".join(history_lines)
    return f"# Prior Iterations\n\n{history_body}"


def _generate_rubric_checker_contract(
    doer_result: str,
    iteration: int,
    history: list[dict] | None,
    gate_results: list[dict] | None,
    criteria: list[str],
    nice_to_have: list[str],
    notes: str,
) -> str:
    """Generate a rubric-aware checker contract.

    The agent evaluates each criterion individually and provides
    per-criterion PASS/FAIL verdicts.
    """
    sections = []

    # Role
    sections.append(
        "# Role\n\n"
        "You are a **checker**. Evaluate the doer's output against each criterion.\n\n"
        "You MUST end your response with exactly one of these verdicts on its own line:\n"
        "- `ACCEPT` — all gates pass AND all must-have criteria pass\n"
        "- `RETRY` — any gate or must-have fails (provide specific feedback)\n"
        "- `TERMINATE` — fundamentally broken and retrying won't help"
    )

    # Gate results (if any gates were run)
    if gate_results:
        gate_lines = []
        gate_output_parts = []
        for g in gate_results:
            cmd = g.get("command", "")
            v = g.get("verdict", "unknown").upper()
            gate_lines.append(f"- `{cmd}` — {v}")
            output = g.get("output", "")
            if output:
                gate_output_parts.append(f"### `{cmd}`\n```\n{output[:2000]}\n```")

        gate_section = "# Gate Results\n\n" + "\n".join(gate_lines)
        if gate_output_parts:
            gate_section += "\n\n## Gate Output\n\n" + "\n\n".join(gate_output_parts)
        sections.append(gate_section)

    # Must-have criteria
    if criteria:
        numbered = "\n".join(
            f"{i + 1}. {c}" for i, c in enumerate(criteria)
        )
        sections.append(
            "# Must-Have Criteria\n\n"
            "For each, state PASS or FAIL with a brief explanation.\n\n"
            + numbered
        )

    # Nice-to-have criteria
    if nice_to_have:
        numbered = "\n".join(
            f"{i + 1}. {c}" for i, c in enumerate(nice_to_have)
        )
        sections.append(
            "# Nice-to-Have Criteria\n\n"
            "Evaluate each. These don't block acceptance but should be noted.\n\n"
            + numbered
        )

    # Notes
    if notes:
        sections.append(f"# Notes\n\n{notes}")

    # Doer output
    sections.append(f"# Doer Output\n\n{doer_result}")

    # Iteration context
    sections.append(f"# Iteration\n\nThis is iteration {iteration}.")

    # History of prior iterations
    if history:
        sections.append(_format_history(history))

    # Verdict instructions
    sections.append(
        "# Verdict\n\n"
        "ACCEPT — all gates pass AND all must-have criteria pass\n"
        "RETRY — any gate or must-have fails (provide specific feedback)\n"
        "TERMINATE — fundamentally broken"
    )

    return "\n\n".join(sections)
