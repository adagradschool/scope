"""Contract generation for scope sessions.

Generates markdown contracts that are sent to Claude Code as the initial prompt.
"""

# Known pattern phases — used for pattern commitment tracking
PATTERN_PHASES: dict[str, list[str]] = {
    "tdd": ["red", "green", "refactor"],
    "ralph": ["critique", "improve"],
    "map-reduce": ["map", "wait", "reduce"],
    "maker-checker": ["make", "check", "fix"],
    "dag": [],  # DAG phases are task-specific
    "rlm": ["peek", "grep", "dive"],
}


def generate_contract(
    prompt: str,
    depends_on: list[str] | None = None,
    *,
    phase: str | None = None,
    parent_intent: str | None = None,
    prior_results: list[str] | None = None,
    file_scope: list[str] | None = None,
    verify: list[str] | None = None,
    pattern: str | None = None,
    termination: list[str] | None = None,
    max_iterations: int | None = None,
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
        pattern: Optional pattern commitment (e.g., 'tdd', 'ralph').
        termination: Optional list of termination criteria for loop control.
        max_iterations: Optional max iteration bound for loop control.

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

    # Add pattern commitment
    if pattern:
        pattern_lower = pattern.lower()
        phases = PATTERN_PHASES.get(pattern_lower, [])
        if phases:
            phases_str = " → ".join(phases)
            section = (
                f"# Pattern Commitment\n\n"
                f"You are committed to the **{pattern_lower}** pattern.\n\n"
                f"Phases: {phases_str}\n\n"
                f"Follow this pattern's phases in order. If you need to deviate, "
                f"you MUST explicitly state why before doing so — drift must be conscious, not accidental."
            )
        else:
            section = (
                f"# Pattern Commitment\n\n"
                f"You are committed to the **{pattern_lower}** pattern.\n\n"
                f"Follow this pattern's workflow. If you need to deviate, "
                f"you MUST explicitly state why before doing so — drift must be conscious, not accidental."
            )
        sections.append(section)

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

    # Add termination criteria section
    if termination:
        criteria = "\n".join(f"- {c}" for c in termination)
        bound = f" (max {max_iterations} iterations)" if max_iterations else ""
        sections.append(
            f"# Termination Criteria\n\n"
            f"This session is part of a feedback loop{bound}. "
            f"The loop completes when:\n{criteria}\n\n"
            f"After each iteration, these criteria will be checked and the orchestrator "
            f"will receive a recommendation to terminate or continue."
        )

    return "\n\n".join(sections)
