"""Shared summarization utility.

Provides a single low-level function that handles the claude -p call,
env sanitization, timeout, fallback, and length validation.
"""

import os
import subprocess


def summarize(
    content: str,
    *,
    goal: str,
    max_length: int = 300,
    fallback: str = "",
) -> str:
    """Summarize content using Claude CLI.

    Args:
        content: The text to summarize.
        goal: A plain English instruction describing the desired summary
              (e.g. '3-5 word task title', '1-2 sentence progress summary').
        max_length: Maximum allowed length of the summary. Responses longer
                    than this are discarded and the fallback is returned.
        fallback: Value to return if the Claude call fails or produces
                  an invalid result.

    Returns:
        The summary string, or *fallback* on failure.
    """
    try:
        # Remove SCOPE_SESSION_ID to prevent hook recursion
        env = os.environ.copy()
        env.pop("SCOPE_SESSION_ID", None)

        result = subprocess.run(
            [
                "claude",
                "-p",
                f"{goal}\n\n{content}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode == 0 and result.stdout.strip():
            summary = result.stdout.strip()
            if len(summary) <= max_length:
                return summary

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return fallback
