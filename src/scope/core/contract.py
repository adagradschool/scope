"""Contract generation for scope sessions.

Generates markdown contracts that are sent to Claude Code as the initial prompt.
"""


def generate_contract(prompt: str) -> str:
    """Generate a contract markdown for a session.

    The contract is sent to Claude Code as the initial prompt via tmux send-keys.

    Args:
        prompt: The initial prompt/context to send to Claude Code.

    Returns:
        Markdown string containing the contract.
    """
    return f"# Task\n\n{prompt}"
