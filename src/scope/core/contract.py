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
) -> str:
    """Generate a checker contract for verifying doer output.

    The checker sees the doer's result (not its reasoning/trajectory),
    iteration history, and is asked to render a verdict.

    Args:
        checker_prompt: The checker's verification prompt.
        doer_result: The doer's final output text.
        iteration: Current iteration number (0-indexed).
        history: Prior iteration records with keys: iteration, verdict, feedback.

    Returns:
        Markdown string containing the checker contract.
    """
    sections = []

    # Role
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
        history_lines = []
        for entry in history:
            verdict = entry.get("verdict", "unknown").upper()
            feedback = entry.get("feedback", "")
            line = f"- Iteration {entry.get('iteration', '?')}: **{verdict}**"
            if feedback:
                line += f" — {feedback}"
            history_lines.append(line)
        history_body = "\n".join(history_lines)
        sections.append(f"# Prior Iterations\n\n{history_body}")

    return "\n\n".join(sections)
