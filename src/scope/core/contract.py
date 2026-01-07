"""Contract generation for scope sessions.

Generates markdown contracts that are sent to Claude Code as the initial prompt.
"""


def generate_contract(prompt: str, depends_on: list[str] | None = None) -> str:
    """Generate a contract markdown for a session.

    The contract is sent to Claude Code as the initial prompt via tmux send-keys.

    Args:
        prompt: The initial prompt/context to send to Claude Code.
        depends_on: Optional list of session IDs this session depends on.
            If provided, the contract will include instructions to wait for
            these dependencies before starting work.

    Returns:
        Markdown string containing the contract.
    """
    sections = []

    # Invoke /scope command to load orchestration rules
    sections.append("/scope")

    # Add dependencies section if there are dependencies
    if depends_on:
        deps_str = " ".join(depends_on)
        sections.append(
            f"# Dependencies\n\n"
            f"Before starting, wait for your dependencies to complete:\n"
            f"```bash\nscope wait {deps_str}\n```\n\n"
            f"Use the results from these sessions to inform your work."
        )

    # Add task section
    sections.append(f"# Task\n{prompt}")

    return "\n\n".join(sections)
