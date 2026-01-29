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

    return "\n\n".join(sections)
